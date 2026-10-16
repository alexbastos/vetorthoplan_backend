#!/usr/bin/env python3
"""Exercise image upload, asynchronous ingestion, READY state, and preview retrieval."""

from __future__ import annotations

import hashlib
import io
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, ImageDraw

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
TIMEOUT_SECONDS = int(os.getenv("SMOKE_TIMEOUT_SECONDS", "120"))
POLL_INTERVAL_SECONDS = float(os.getenv("SMOKE_POLL_INTERVAL_SECONDS", "2"))
SYNTHETIC_FILENAME = "vetorthoplan-smoke-synthetic.png"


class SmokeTestError(RuntimeError):
    pass


def fail_for_response(response: httpx.Response, action: str) -> None:
    if response.is_success:
        return
    # Never include a URL in errors: upload and preview URLs are temporary credentials.
    try:
        body: Any = response.json()
    except ValueError:
        body = response.text[:500]
    if isinstance(body, dict):
        body.pop("url", None)
        detail = body.get("detail", body)
    else:
        detail = body
    raise SmokeTestError(f"{action}: HTTP {response.status_code}; resposta: {detail}")


def make_synthetic_png() -> bytes:
    image = Image.new("L", (640, 480), color=18)
    draw = ImageDraw.Draw(image)
    draw.ellipse((190, 45, 450, 430), fill=95)
    draw.line((320, 65, 320, 415), fill=230, width=9)
    draw.line((320, 230, 215, 125), fill=190, width=7)
    draw.line((320, 230, 420, 335), fill=190, width=7)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def request_json(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    action: str,
    **kwargs: Any,
) -> dict[str, Any]:
    response = client.request(method, f"{API_BASE_URL}{path}", **kwargs)
    fail_for_response(response, action)
    try:
        result = response.json()
    except ValueError as exc:
        raise SmokeTestError(f"{action}: API retornou conteúdo que não é JSON") from exc
    if not isinstance(result, dict):
        raise SmokeTestError(f"{action}: formato JSON inesperado")
    return result


def run() -> None:
    if TIMEOUT_SECONDS <= 0 or POLL_INTERVAL_SECONDS <= 0:
        raise SmokeTestError("Timeout e intervalo de polling devem ser maiores que zero")

    png_bytes = make_synthetic_png()
    sha256 = hashlib.sha256(png_bytes).hexdigest()
    marker = uuid.uuid4().hex[:12]

    print(f"API: {API_BASE_URL}")
    print("Este smoke test cria um caso e uma imagem sintéticos, que permanecem no banco.")

    with httpx.Client(timeout=30, follow_redirects=True) as client:
        health = client.get(f"{API_BASE_URL}/health/live")
        fail_for_response(health, "Health check")
        print("[OK] API disponível")

        case = request_json(
            client,
            "POST",
            "/api/v1/cases",
            action="Criar caso sintético",
            json={
                "title": f"SMOKE teste de ingestão {marker}",
                "animal_name": f"Paciente sintético {marker}",
                "species": "Canina",
                "clinical_notes": "Fixture sintética para smoke test; sem dado clínico real.",
            },
        )
        case_id = case["id"]
        print(f"[OK] Caso criado: {case_id}")

        upload_session = request_json(
            client,
            "POST",
            f"/api/v1/cases/{case_id}/image-uploads",
            action="Criar sessão de upload",
            json={
                "original_filename": SYNTHETIC_FILENAME,
                "media_type": "image/png",
                "size_bytes": len(png_bytes),
                "sha256": sha256,
            },
        )
        image_id = upload_session["image_id"]
        upload = upload_session["upload"]
        if upload.get("method") != "POST":
            raise SmokeTestError("A sessão de upload não retornou método POST")

        # A URL assinada só é utilizada em memória e nunca é exibida.
        storage_response = client.post(
            upload["url"],
            data=upload["fields"],
            files={"file": (SYNTHETIC_FILENAME, png_bytes, "image/png")},
            timeout=60,
        )
        if not storage_response.is_success:
            raise SmokeTestError(
                f"Enviar binário ao object storage: HTTP {storage_response.status_code}"
            )
        print(f"[OK] PNG sintético enviado ao storage ({len(png_bytes)} bytes)")

        completed = request_json(
            client,
            "POST",
            f"/api/v1/image-uploads/{upload_session['upload_id']}/complete",
            action="Confirmar upload e enfileirar ingestão",
        )
        job_id = completed["job_id"]
        print(f"[OK] Upload confirmado; job {job_id} ({completed['job_status']})")

        deadline = time.monotonic() + TIMEOUT_SECONDS
        job: dict[str, Any] = {}
        while time.monotonic() < deadline:
            job = request_json(
                client,
                "GET",
                f"/api/v1/jobs/{job_id}",
                action="Consultar job de ingestão",
            )
            job_status = job["status"]
            print(f"Processamento: {job_status}")
            if job_status in {"SUCCEEDED", "REJECTED", "FAILED"}:
                break
            time.sleep(POLL_INTERVAL_SECONDS)
        else:
            raise SmokeTestError(
                f"Timeout aguardando processamento após {TIMEOUT_SECONDS}s; job {job_id}"
            )

        if job.get("status") != "SUCCEEDED":
            raise SmokeTestError(
                f"Job terminou em {job.get('status')} (error_code={job.get('error_code')})"
            )
        print("[OK] Job concluído com sucesso")

        images = request_json(
            client,
            "GET",
            f"/api/v1/cases/{case_id}/images",
            action="Listar imagens do caso",
        )
        image = next((item for item in images.get("items", []) if item["id"] == image_id), None)
        if image is None:
            raise SmokeTestError("Imagem processada não apareceu na lista do caso")
        if image.get("status") != "READY" or not image.get("preview_available"):
            raise SmokeTestError(
                "Imagem não está pronta: "
                f"status={image.get('status')}, preview_available={image.get('preview_available')}"
            )
        print(
            "[OK] Imagem READY; dimensões originais: "
            f"{image.get('width_px')}x{image.get('height_px')}"
        )

        preview = request_json(
            client,
            "GET",
            f"/api/v1/images/{image_id}/preview",
            action="Obter acesso à prévia",
        )
        preview_response = client.get(preview["url"], timeout=60)
        if not preview_response.is_success:
            raise SmokeTestError(
                f"Download da prévia: HTTP {preview_response.status_code}"
            )
        content_type = preview_response.headers.get("content-type", "").split(";", 1)[0]
        if content_type != preview.get("media_type"):
            raise SmokeTestError(
                f"Tipo da prévia divergente: API={preview.get('media_type')}, storage={content_type}"
            )
        try:
            with Image.open(io.BytesIO(preview_response.content)) as preview_image:
                preview_image.verify()
            with Image.open(io.BytesIO(preview_response.content)) as preview_image:
                dimensions = preview_image.size
                image_format = preview_image.format
        except Exception as exc:
            raise SmokeTestError(f"A prévia baixada não é uma imagem válida: {exc}") from exc

        expected_dimensions = (preview["width_px"], preview["height_px"])
        if dimensions != expected_dimensions:
            raise SmokeTestError(
                f"Dimensões da prévia divergentes: API={expected_dimensions}, arquivo={dimensions}"
            )
        if image_format != "PNG":
            raise SmokeTestError(f"Formato da prévia deveria ser PNG, recebido: {image_format}")

        preview_path = Path(
            os.getenv("SMOKE_PREVIEW_OUTPUT", f"/tmp/vetorthoplan-smoke-preview-{marker}.png")
        )
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        preview_path.write_bytes(preview_response.content)

        print(
            "[OK] Prévia baixada e decodificada: "
            f"{image_format} {dimensions[0]}x{dimensions[1]}, {len(preview_response.content)} bytes"
        )
        print(f"Arquivo para inspeção visual: {preview_path}")
        print(f"Caso: {case_id} | Imagem: {image_id} | Job: {job_id}")
        print("RESULTADO: fluxo completo até READY e prévia validada.")


if __name__ == "__main__":
    try:
        run()
    except (httpx.HTTPError, KeyError, SmokeTestError, ValueError) as exc:
        print(f"FALHA: {exc}", file=sys.stderr)
        sys.exit(1)
