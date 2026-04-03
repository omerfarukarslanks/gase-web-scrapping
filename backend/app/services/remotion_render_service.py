import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class RemotionRenderService:
    def __init__(self, frontend_path: str | None = None):
        # Backend dizininden frontend dizinini otomatik buluyoruz
        base_dir = Path(__file__).resolve().parent.parent.parent.parent
        self.frontend_path = Path(frontend_path) if frontend_path else base_dir / "frontend"

    def render_mp4(self, composition_id: str, payload: dict[str, Any], output_filename: str = "output.mp4") -> str:
        output_path = self.frontend_path / "out" / output_filename
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Remotion'ın JSON verisini okuyabilmesi için geçici bir props dosyası oluşturuyoruz
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp_file:
            json.dump(payload, tmp_file)
            props_file_path = tmp_file.name

        try:
            logger.info(f"Starting Remotion render for {composition_id}...")
            
            # Örn komut: npx remotion render src/index.ts PromptVideo out/output.mp4 --props=temp.json
            command = [
                "npx",
                "remotion",
                "render",
                "src/remotion/index.ts",  # Frontend'deki ana Remotion entry dosyanız (yolu projenize göre güncelleyebilirsiniz)
                composition_id,
                str(output_path),
                f"--props={props_file_path}",
            ]

            result = subprocess.run(
                command, cwd=self.frontend_path, capture_output=True, text=True, check=True
            )
            logger.info(f"Render completed successfully: {output_path}")
            return str(output_path)
        except subprocess.CalledProcessError as exc:
            logger.error(f"Remotion render failed! Error: {exc.stderr}")
            raise RuntimeError(f"Video render failed: {exc.stderr}") from exc
        finally:
            if os.path.exists(props_file_path):
                os.remove(props_file_path)