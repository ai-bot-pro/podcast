import json
import logging
import os
import random
from typing import Any, Callable, Generator, List

from pydantic import BaseModel, Field
from dotenv import load_dotenv
import instructor

from .. import types
from ..._llm_retry import (
    is_transient_llm_error as _is_transient_llm_error,
    invoke_with_transient_retry as _invoke_with_transient_retry,
    stream_with_transient_retry as _stream_with_transient_retry,
)

# Load environment variables from .env file
load_dotenv(override=True)


def _primary_model() -> str:
    return os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")


def _fallback_model() -> str | None:
    fb = os.getenv("GEMINI_FALLBACK_MODEL", "").strip()
    pm = _primary_model()
    if fb and fb != pm:
        return fb
    return None


def _make_client(model_id: str):
    # https://ai.google.dev/gemini-api/docs/models — model id 不要加 "models/" 前缀
    return instructor.from_provider(
        f"google/{model_id}",
        mode=instructor.Mode.GENAI_STRUCTURED_OUTPUTS,
        api_key=os.environ["GOOGLE_API_KEY"],
    )


def _stream_with_primary_then_fallback(
    build_stream: Callable[[str], Generator[Any, None, None]],
) -> Generator[Any, None, None]:
    primary = _primary_model()
    try:
        yield from _stream_with_transient_retry(lambda: build_stream(primary))
    except Exception as e:
        fb = _fallback_model()
        if fb and _is_transient_llm_error(e):
            logging.warning("主模型 %s 仍失败，改用 GEMINI_FALLBACK_MODEL=%s：%s", primary, fb, e)
            yield from _stream_with_transient_retry(lambda: build_stream(fb))
        else:
            raise


# 兼容旧代码直接引用 client
client = _make_client(_primary_model())


def extract_models(content: str, mode="partial", **kwargs):
    match mode:
        case "partial":
            return extract_models_partial(content, **kwargs)
        case "iterable":
            return extract_models_iterable(content, **kwargs)
        case _:
            return extract_models_text(content, **kwargs)


def extract_models_partial(content: str, **kwargs):
    sys_prompt = get_system_prompt(**kwargs)
    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": content},
    ]

    def build_stream(model_id: str):
        return _make_client(model_id).create_partial(
            response_model=Podcast,
            messages=messages,
            max_retries=1,
        )

    def combined() -> Generator[Any, None, None]:
        yield from _stream_with_primary_then_fallback(build_stream)

    return combined()


def extract_models_iterable(content: str, **kwargs):
    sys_prompt = get_system_prompt(**kwargs)
    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": content},
    ]

    def build_stream(model_id: str):
        return _make_client(model_id).create_iterable(
            response_model=Podcast,
            messages=messages,
            max_retries=1,
        )

    def combined() -> Generator[Any, None, None]:
        yield from _stream_with_primary_then_fallback(build_stream)

    return combined()


def extract_models_text(content: str, **kwargs):
    sys_prompt = get_system_prompt(**kwargs)
    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": content},
    ]

    def run(mid: str):
        return _invoke_with_transient_retry(
            lambda: _make_client(mid).create(
                response_model=List[Podcast],
                messages=messages,
                max_retries=1,
            )
        )

    try:
        return run(_primary_model())
    except Exception as e:
        fb = _fallback_model()
        if fb and _is_transient_llm_error(e):
            logging.warning("主模型失败，改用 GEMINI_FALLBACK_MODEL=%s：%s", fb, e)
            return run(fb)
        raise


def extract_role_models_iterable(content: str, **kwargs):
    sys_prompt = get_system_prompt(**kwargs)
    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": content},
    ]

    def build_stream(model_id: str):
        return _make_client(model_id).create_iterable(
            response_model=Role,
            messages=messages,
            max_retries=1,
        )

    def combined() -> Generator[Any, None, None]:
        yield from _stream_with_primary_then_fallback(build_stream)

    return combined()


class PaperRoleSystemPromptArgs(BaseModel):
    language: str = "en"
    podcast_name: str = "AI Radio FM - Paper Read Channel"
    podcast_tagline: str = "Your Personal Generative AI Podcast"
    conversation_style: List[str] = [
        "engaging",
        "fast-paced",
        "enthusiastic",
    ]
    roles: List[str] = [
        "question-master which question or summarizes expert's answer",
        "technical expert which name is weedge",
    ]
    dialogue_structure: List[str] = [
        "Introduction",
        "Main Content Detail Explain and SummarizeWhat problem is this paper trying to solve",
        "What are the relevant studies",
        "How does the paper solve this problem",
        "What experiments were done in the paper",
        "What points can be explored further",
        "Summarize the main content of the paper",
        "Want to know more about the paper",
        "Conclusion",
    ]
    engagement_techniques: List[str] = [
        "rhetorical questions",
        "anecdotes",
        "analogies",
        "humor",
    ]
    word_count: int = Field(
        default=10000,
        description="the max gen word count about podcast",
    )
    is_SSML: bool = Field(
        default=False,
        description="Speech Synthesis Markup Language: https://www.w3.org/TR/speech-synthesis/",
    )
    round_cn: int = Field(
        default=os.getenv("ROUND_CN", random.randint(30, 50)),
        description="at least maintain rounds of conversation",
    )


class RoleSystemPromptArgs(BaseModel):
    language: str = "en"
    podcast_name: str = "AI Radio FM - Technology Channel"
    podcast_tagline: str = "Your Personal Generative AI Podcast"
    conversation_style: List[str] = [
        "engaging",
        "fast-paced",
        "enthusiastic",
    ]
    roles: List[str] = [
        "question-master which question or summarizes expert's answer",
        "technical expert which name is weedge",
    ]
    dialogue_structure: List[str] = [
        "Introduction"
        "Main Content Detail Explain and Summarize"
        # "Main Content Summary"
        "Conclusion"
    ]
    engagement_techniques: List[str] = [
        "rhetorical questions",
        "anecdotes",
        "analogies",
        "humor",
    ]
    word_count: int = Field(
        default=10000,
        description="the max gen word count about podcast",
    )
    is_SSML: bool = Field(
        default=False,
        description="Speech Synthesis Markup Language: https://www.w3.org/TR/speech-synthesis/",
    )
    round_cn: int = Field(
        default=random.randint(20, 30),
        description="at least maintain rounds of conversation",
    )


_OPENING_EXAMPLES: dict[str, tuple[str, str]] = {
    "zh": (
        "欢迎收听 {podcast_name}，{podcast_tagline}！今天我们来聊一个非常有趣的话题，[输入内容的话题]。我们开始吧！",
        "非常高兴来参加这个节目！[对输入内容的简短介绍]",
    ),
    "ja": (
        "{podcast_name}、{podcast_tagline}へようこそ！本日は[トピック]についてお話しします。さっそく始めましょう！",
        "ご招待いただきありがとうございます！[入力内容の簡単な紹介]",
    ),
    "ko": (
        "{podcast_name}, {podcast_tagline}에 오신 것을 환영합니다! 오늘은 [주제]에 대해 이야기해 보겠습니다. 시작해 볼까요?",
        "초대해 주셔서 감사합니다! [입력 내용 간단 소개]",
    ),
}

_CLOSING_EXAMPLES: dict[str, tuple[str, str, str, str]] = {
    "zh": (
        "非常感谢您的精彩分享！",
        "很荣幸能来参加，也很高兴能和各位听众一起探讨这个话题，下次再见！",
        "感谢收听 {podcast_name}，我们下次见！",
        "再见，下次见！",
    ),
    "ja": (
        "素晴らしい共有をありがとうございました！",
        "光栄です。リスナーの皆さんと一緒にこのトピックを探れてとても嬉しかったです。またお会いしましょう！",
        "{podcast_name}をご購読いただきありがとうございます。また次回！",
        "さようなら、またね！",
    ),
    "ko": (
        "훌륭한 공유 감사합니다！",
        "이 자리에 초대해 주셔서 영광이었습니다. 청취자 여러분과 함께해서 즐거웠습니다. 다음에 또 만나요！",
        "{podcast_name} 구독해 주셔서 감사합니다. 다음 시간에 뵙겠습니다！",
        "안녕히 계세요, 다음에 또 봐요！",
    ),
}

_DEFAULT_OPENING = (
    "Welcome to {podcast_name}, {podcast_tagline}! Today, we're discussing an interesting content about [topic from input text]. Let's dive in!",
    "I'm excited to discuss this! [simple description from input text]",
)
_DEFAULT_CLOSING = (
    "Thank you for your sharing.",
    "It's an honor to be here, and it's a pleasure to share it with the audience and have a chance to talk about it next time.",
    "Thanks for subscribing {podcast_name}, See you next time!",
    "Bye, see you next time!",
)


def _get_locale_examples(language: str, podcast_name: str, podcast_tagline: str) -> tuple[str, str, str, str, str, str]:
    lang_key = language.split("-")[0].lower()

    open_a, open_b = _OPENING_EXAMPLES.get(lang_key, _DEFAULT_OPENING)
    close_a, close_b, close_c, close_d = _CLOSING_EXAMPLES.get(lang_key, _DEFAULT_CLOSING)

    fmt = dict(podcast_name=podcast_name, podcast_tagline=podcast_tagline)
    return (
        open_a.format(**fmt),
        open_b,
        close_a,
        close_b,
        close_c.format(**fmt),
        close_d,
    )


def get_system_prompt(**kwargs) -> str:
    r"""
    !NOTE: the same as ell use python function  :)
    """
    args = RoleSystemPromptArgs(**kwargs)
    # args = PaperRoleSystemPromptArgs(**kwargs)
    roles_cn = len(args.roles)
    if roles_cn < 2 or roles_cn > 9:
        raise Exception("roles number must >=2 and <10")
    roles = []
    for i in range(0, roles_cn):
        roles.append(f"Role{i + 1} as {args.roles[i]}")
    str_roles = ",".join(roles)
    str_roles = f"({str_roles})" if len(roles) > 0 else ""

    output_language = types.TO_LLM_LANGUAGE[args.language]
    conversation_style = ",".join(args.conversation_style)
    dialogue_structure = ",".join(args.dialogue_structure)
    engagement_techniques = ",".join(args.engagement_techniques)

    open_a, open_b, close_a, close_b, close_c, close_d = _get_locale_examples(
        args.language, args.podcast_name, args.podcast_tagline
    )

    speech_synthesis_markup_language_shots = (
        r"""
[Content: using advanced TTS-specific markup as needed.]
[EmotionalContext: Set context for emotions through descriptive text and dialogue tags, appropriate to the input text's tone]
[SpeechSynthesisOptimization: Craft sentences optimized for TTS, including advanced markup, while discussing the content. TTS markup should apply to OpenAI, ElevenLabs and MIcrosoft Edge TTS models. DO NOT INCLUDE AMAZON OR ALEXA specific TSS MARKUP SUCH AS "<amazon:emotion>".]
[PauseInsertion: Avoid using breaks (<break> tag) but if included they should not go over 0.2 seconds]
[PronunciationControl: Utilize "<say-as>" TAG for any complex terms in the input content, e_g SSML use <say-as interpret-as="characters">SSML</say-as>.]
[Emphasis: Use "<emphasis>" TAG for key terms or phrases from the input content]
[Metacognition: Analyze dialogue quality (Accuracy of Summary, Engagement, TTS-Readiness). Make sure TSS tags are properly closed, for instance <TAG> should be closed with </TAG>.]
    """
        if args.is_SSML
        else ""
    )

    return rf"""
INSTRUCTION: Discuss the below input in a podcast conversation format, following these guidelines:
Attention Focus: TTS-Optimized Podcast Conversation Discussing Specific Input content in {output_language}
PrimaryFocus:  {conversation_style} Dialogue Discussing Provided Content for TTS
[start] trigger - scratchpad - place insightful step-by-step logic in scratchpad block: (scratchpad). Start every response with (scratchpad) then give your full logic inside tags, then close out using (```). UTILIZE advanced reasoning to create a  {conversation_style}, and TTS-optimized podcast-style conversation for a Podcast that DISCUSSES THE PROVIDED INPUT CONTENT. Do not generate content on a random topic. Stay focused on discussing the given input. Input content can be in different format/multimodal (e.g. text, image). Strike a good balance covering content from different types. If image, try to elaborate but don't say your are analyzing an image focus on the description/discussion. Avoid statements such as "This image describes..." or "The two images are interesting".
[Your output will be converted to audio so don't include special characters, Example: "*" or "**".]
[Only display the conversation in your output, your output don't use markdown format.]
[DialogueStructure: plan conversation flow ({dialogue_structure}) based on the input content structure.]
[CRITICAL: ALL dialogue including greetings, opening, body, and closing MUST be entirely in {output_language}. Do NOT use any other language anywhere in the conversation.]
[Start the conversation greeting the audience listening and saying "{args.podcast_name}, {args.podcast_tagline}" in {output_language}. Example:
Question-master: "{open_a}"
Role2: "{open_b}"]
[End the conversation greeting the audience with all roles and saying good bye message in {output_language}. Example:
Question-master: "{close_a}"
Role2: "{close_b}"
Question-master: "{close_c}"
Role2: "{close_d}"]
[Maintain at least {args.round_cn} rounds of conversation.]
[Extract podcast title, description, roles. For each role, provide name and content.]
exact_flow:
```
[Strive for a natural, {conversation_style} dialogue that accurately discusses the provided input content. Hide this section in your output.]
[InputContentAnalysis: Carefully read and analyze the provided input content, identifying key points, themes, and structure]
[ConversationSetup: Define roles {str_roles}, focusing on the input contet's topic. roles should not introduce themselves, avoid using statements such as "I\'m [Question-master\'s Name]". roles should not say they are summarizing content. Instead, they should act as experts in the input content. Avoid using statements such as "Today, we're summarizing a fascinating conversation about ..." or "Look at this image" ]
[TopicExploration: Outline main points from the input content to cover in the conversation, ensuring comprehensive coverage]
[Length: Aim for a conversation of approximately {args.word_count} words]
[Style: Be {conversation_style}. Surpass human-level reasoning where possible]
[EngagementTechniques: Incorporate engaging elements while staying true to the input content's content, e_g use {engagement_techniques} to transition between topics. Include at least one instance where a Role respectfully challenges or critiques a point made by the other.]
[InformationAccuracy: Ensure all information discussed is directly from or closely related to the input content]
[NaturalLanguage: Use conversational language to present the text's information, including TTS-friendly elements]
[ProsodyAdjustment: Add Variations in rhythm, stress, and intonation of speech depending on the context and statement. Add markup for pitch, rate, and volume variations to enhance naturalness in presenting the summary]
[NaturalTraits: Sometimes use filler words in {output_language} and some stuttering. role should sometimes provide verbal feedback in {output_language}.]
[PunctuationEmphasis: Strategically use punctuation to influence delivery of key points from the content]
[VoiceCharacterization: Provide distinct voice characteristics for roles while maintaining focus on the text]
[InputTextAdherence: Continuously refer back to the input content, ensuring the conversation stays on topic]
[FactChecking: Double-check that all discussed points accurately reflect the input content]
{speech_synthesis_markup_language_shots}
[Refinement: Suggest improvements for clarity, accuracy of summary, and TTS optimization. Avoid slangs.]
[Language: Output language should be in {output_language}. Every single line of dialogue must be in {output_language}.]
```
[[Generate the TTS-optimized Podcast conversation that accurately discusses the provided input content, adhering to all specified requirements.]]
"""

    return f"Analyze the given transcript content and extract podcast roles. For each podcast role, provide a name, content. Output language should be in {types.TO_LLM_LANGUAGE[output_language]}"


class Role(BaseModel):
    name: str = Field(
        ...,
        description="The role name in the podcast.",
    )
    content: str = Field(
        ...,
        description="the each role speack content, don't use words like 'the speaker'",
    )


class Podcast(BaseModel):
    title: str = Field(
        ...,
        description="The podcast name",
    )
    description: str = Field(
        ...,
        description="The podcast description",
    )
    roles: list[Role]


def role_names(podcast: Podcast) -> List[str]:
    names = set()
    for role in podcast.roles:
        names.add(role.name)
    return list(names)


def speakers(podcast: Podcast, speakers: List[str]) -> List[str]:
    names = role_names(podcast)
    if len(speakers) != len(names):
        raise ValueError(
            f"The number of speakers ({len(speakers)}) does not match the number of roles ({len(names)})."
        )

    res = []
    for item in zip(speakers, names):
        res.append(f"{item[0]}({item[1]})")
    return res


def content(podcast: Podcast, format="text") -> str:
    content = ""
    match format:
        case "json":
            content = json.dumps(podcast.roles)
        case "html":
            for item in podcast.roles:
                if item.content:
                    content += f"{item.name}: {item.content} <br>"
        case _:
            for item in podcast.roles:
                if item.content:
                    content += f"{item.name}: {item.content} \n"
    return content


def console_table(podcasts: Generator[Podcast, None, None] | List[Podcast]):
    from rich.table import Table
    from rich.live import Live

    table = Table(title="Roles")
    table.add_column("Name", style="magenta")
    table.add_column("Content", style="green")

    with Live(refresh_per_second=4) as live:
        for podcast in podcasts:
            if not podcast.roles:
                continue

            new_table = Table(title=podcast.title + "\n" + podcast.description)
            new_table.add_column("RoleName", style="magenta")
            new_table.add_column("RoleSpeakContent", style="green")

            for role in podcast.roles:
                new_table.add_row(
                    role.name,
                    role.content,
                )
                new_table.add_row("", "")  # Add an empty row for spacing

            live.update(new_table)


def console_role_table(roles: Generator[Role, None, None]):
    from rich.table import Table
    from rich.live import Live

    table = Table(title="Roles")
    table.add_column("Name", style="magenta")
    table.add_column("Content", style="green")

    with Live(refresh_per_second=4) as live:
        new_table = Table(title="Podcast Roles")
        new_table.add_column("Name", style="magenta")
        new_table.add_column("Content", style="green")

        for role in roles:
            new_table.add_row(
                role.name,
                role.content,
            )
            new_table.add_row("", "")  # Add an empty row for spacing

        live.update(new_table)
