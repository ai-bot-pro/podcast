import base64
import io
import os
import logging
import time
from typing import Any, List

import typer
from dotenv import load_dotenv
import requests


# Load environment variables from .env file
load_dotenv(override=True)

app = typer.Typer()


def _siliconflow_error_message(body: dict) -> str | None:
    """Return a human-readable error string, or None if body looks successful."""
    err = body.get("error")
    if err is not None:
        if isinstance(err, dict):
            return str(err.get("message", err))
        return str(err)
    code = body.get("code", 0)
    data = body.get("data")
    if code != 0 and not data:
        return str(body.get("message") or f"code={code}")
    return None


@app.command("gen_image")
def gen_image(
    prompt: str,
    width: int = 1024,
    height: int = 1024,
    steps: int = 20,
    n: int = 1,
    guidance_scale: float = 7.5,
) -> List[str]:
    url = "https://api.siliconflow.cn/v1/images/generations"

    payload = {
        "batch_size": n,
        "num_inference_steps": steps,
        "guidance_scale": guidance_scale,
        "model": "Kwai-Kolors/Kolors",
        "prompt": prompt,
        "image_size": f"{width}x{height}",
    }
    api_key = os.getenv("SILICONCLOUD_API_KEY")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    while True:
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=120)
            try:
                body: Any = resp.json()
            except ValueError:
                raise RuntimeError(
                    f"SiliconFlow non-JSON response HTTP {resp.status_code}: "
                    f"{resp.text[:800]!r}"
                ) from None
            if not isinstance(body, dict):
                raise RuntimeError(
                    f"SiliconFlow JSON root must be an object, got {type(body).__name__}: "
                    f"{repr(body)[:400]}"
                )
            msg = _siliconflow_error_message(body)
            if msg:
                raise RuntimeError(msg)
            data = body.get("data")
            if data is None:
                raise RuntimeError(
                    "SiliconFlow response missing 'data' "
                    f"(HTTP {resp.status_code}): {repr(body)[:400]}"
                )
        except Exception as e:
            logging.error(f"requests error: {e}")
            time.sleep(3)
            continue
        break

    return data


@app.command("save_image_from_url")
def save_image_from_url(
    url: str,
    file_name: str,
    save_dir: str = "./images",
):
    assert url, "url is empty"
    os.makedirs(save_dir, exist_ok=True)

    try:
        response = requests.get(url)
        response.raise_for_status()

        content_type = response.headers.get("content-type", "")
        if "png" in content_type:
            ext = "png"
        elif "jpeg" in content_type or "jpg" in content_type:
            ext = "jpg"
        else:
            ext = "png"

        save_path = os.path.join(save_dir, f"{file_name}.{ext}")

        with open(save_path, "wb") as f:
            f.write(response.content)

        logging.info(f"image save to: {save_path}")
        return save_path

    except requests.exceptions.RequestException as e:
        logging.error(f"requests error: {e}")
        raise typer.Exit(code=1)


@app.command("save_gen_image")
def save_gen_image(
    prompt: str,
    file_name: str,
    save_dir: str = "./images",
    width: int = 1024,
    height: int = 1024,
    n: int = 1,
):
    img_data = gen_image(prompt, width=width, height=height, n=n)
    if not img_data:
        raise Exception("no gen image")

    for img in img_data:
        if isinstance(img, dict):
            url = img.get("url", "") or ""
        elif isinstance(img, str):
            url = img
        else:
            logging.warning(f"skip unexpected image entry type {type(img)}: {img!r}")
            continue
        if url:
            return save_image_from_url(url=url, file_name=file_name, save_dir=save_dir)
    raise ValueError("no image URL in SiliconFlow response data")


r"""
python -m podcast.siliconflow_api gen_image "llama, sitting in a field of flowers"
python -m podcast.siliconflow_api save_gen_image "llama, sitting in a field of flowers" llama
"""
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(pathname)s:%(lineno)d - %(funcName)s - %(message)s",
        handlers=[logging.StreamHandler()],
    )
    app()
