#!/usr/bin/env python3
"""Create a text summary and a visual-notes infographic for a paper (PDF).

Usage:
    visual-notes.py paper.pdf [--style ref.png] [--text-model M] [--image-model M]

Outputs (next to the PDF):
    paper-summary.md
    paper-visual-notes.png

The OpenAI API key is read from ~/.authinfo.gpg, from the line
    machine api.openai.com login <anything> password <key>
"""

import argparse
import base64
import shlex
import subprocess
import sys
from pathlib import Path

from openai import OpenAI

AUTHINFO = Path("~/.authinfo.gpg").expanduser()
MACHINE = "api.openai.com"

EXTRACT_PROMPT = """
Extract content for a detailed academic infographic.

Include:
- Paper title and authors
- Motivation and background
- Research questions
- Methodology and datasets
- Main quantitative findings
- Contributions and implications
- Limitations

Preserve exact numbers and terminology.
Do not invent statistics or conclusions.
Mark anything not established by the paper.
Format the answer as Markdown.
"""

STYLE = """
STYLE:
- Landscape academic infographic poster
- Dense, organized grid of rounded pastel-colored panels
- Bold numbered section headings and colored banners
- Clean vector icons, compact charts and flow diagrams
- Professional typography, high information density
"""


def get_api_key(authinfo=AUTHINFO, machine=MACHINE):
    """Decrypt authinfo with gpg and return the password for `machine`."""
    try:
        out = subprocess.run(
            ["gpg", "--quiet", "--decrypt", str(authinfo)],
            check=True, capture_output=True, text=True,
        ).stdout
    except FileNotFoundError:
        sys.exit("error: gpg not found in PATH")
    except subprocess.CalledProcessError as e:
        sys.exit(f"error: could not decrypt {authinfo}:\n{e.stderr}")

    for line in out.splitlines():
        if line.lstrip().startswith("#"):
            continue
        try:
            tokens = shlex.split(line)
        except ValueError:  # unbalanced quote, e.g. a password containing '
            tokens = line.split()
        fields = dict(zip(tokens[::2], tokens[1::2]))
        if fields.get("machine") == machine and "password" in fields:
            return fields["password"]
    sys.exit(f"error: no 'machine {machine}' entry with a password in {authinfo}")


def summarize(client, pdf_path, model):
    with open(pdf_path, "rb") as f:
        pdf = client.files.create(file=f, purpose="user_data")
    try:
        response = client.responses.create(
            model=model,
            input=[{
                "role": "user",
                "content": [
                    {"type": "input_file", "file_id": pdf.id},
                    {"type": "input_text", "text": EXTRACT_PROMPT},
                ],
            }],
        )
    finally:
        client.files.delete(pdf.id)
    return response.output_text


def make_visual_notes(client, notes, model, style_ref=None):
    reference = (
        "Create a NEW academic infographic using the attached image\n"
        "ONLY as a VISUAL STYLE reference.\n"
        "Do not reuse the reference image's subject matter or facts.\n"
        if style_ref else
        "Create a NEW academic infographic.\n"
    )
    prompt = f"""{reference}
{STYLE}

CONTENT:
{notes}

Represent numerical results faithfully.
Do not invent chart values or findings.
Make all text readable.
"""
    params = dict(model=model, prompt=prompt, size="1536x1024", quality="high")
    if style_ref:
        with open(style_ref, "rb") as ref:
            result = client.images.edit(image=ref, **params)
    else:
        result = client.images.generate(**params)
    return base64.b64decode(result.data[0].b64_json)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("pdf", type=Path, help="paper to process")
    parser.add_argument("--style", type=Path,
                        help="optional image used as a visual style reference")
    parser.add_argument("--text-model", default="gpt-6.1-sol")
    parser.add_argument("--image-model", default="gpt-image-2.5-sunburst")
    args = parser.parse_args()

    if not args.pdf.is_file():
        sys.exit(f"error: {args.pdf} not found")
    if args.style and not args.style.is_file():
        sys.exit(f"error: style reference {args.style} not found")

    summary_path = args.pdf.with_name(args.pdf.stem + "-summary.md")
    image_path = args.pdf.with_name(args.pdf.stem + "-visual-notes.png")

    client = OpenAI(api_key=get_api_key())

    print(f"Summarizing {args.pdf} ...", file=sys.stderr)
    notes = summarize(client, args.pdf, args.text_model)
    summary_path.write_text(notes)
    print(f"Wrote {summary_path}", file=sys.stderr)

    print("Generating visual notes ...", file=sys.stderr)
    image_path.write_bytes(
        make_visual_notes(client, notes, args.image_model, args.style))
    print(f"Wrote {image_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
