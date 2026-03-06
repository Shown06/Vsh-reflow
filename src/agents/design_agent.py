"""
Vsh-reflow - Design-Agent (デザイナー)
画像生成プロンプト作成、fal.ai / DALL-E 3 API連携、画像保存。
"""

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from src.agents.base_agent import BaseAgent
from src.cost_manager import LLMTier, cost_manager
from src.config import settings
from src.models import AgentRole

logger = logging.getLogger(__name__)

IMAGE_OUTPUT_DIR = os.environ.get("IMAGE_OUTPUT_DIR", "/app/generated_images")


class DesignAgent(BaseAgent):
    """デザイナーエージェント"""

    def __init__(self):
        super().__init__(role=AgentRole.DESIGN, name="Design-Agent")

    def _ensure_output_dir(self):
        """画像出力ディレクトリを作成（存在しない場合）"""
        try:
            os.makedirs(IMAGE_OUTPUT_DIR, exist_ok=True)
        except OSError:
            pass  # Docker外実行時はスキップ

    async def execute_task(self, task_code: str, task_type: str, payload: dict) -> dict:
        if task_type == "image_generation":
            return await self._generate_image(task_code, payload)
        elif task_type == "meeting_design":
            return await self._meeting_design(task_code, payload)
        elif task_type == "create_prompt":
            return await self._create_image_prompt(task_code, payload)
        else:
            return {"success": False, "error": f"Unknown task type: {task_type}"}

    async def _generate_image(self, task_code: str, payload: dict) -> dict:
        """画像生成"""
        self._ensure_output_dir()
        description = payload.get("description", "")
        total_cost = 0.0

        # Step 1: LLMで画像生成プロンプトを最適化
        prompt_result = await self.call_llm(
            prompt=f"""以下の説明から、高品質な画像生成AIプロンプトを英語で作成してください。

説明: {description}

以下に注意:
- 具体的なスタイル指定（photorealistic, digital art, etc.）
- 解像度・アスペクト比の推奨
- 色調・雰囲気の指定
- 構図の指定

プロンプトのみを出力してください（説明不要）。""",
            system_prompt="あなたは画像生成AI（DALL-E 3, Midjourney）のプロンプトエンジニアです。",
            tier=LLMTier.DEFAULT,
        )
        total_cost += prompt_result.get("cost_yen", 0.0)

        optimized_prompt = prompt_result.get("text", description)

        # Step 2: 画像生成API呼び出し
        image_path = await self._call_image_api(optimized_prompt, task_code)
        if image_path:
            # 画像生成コスト記録
            image_cost = 6.0  # DALL-E 3概算
            await cost_manager.record_cost(
                service="openai",
                operation="image_generation",
                cost_yen=image_cost,
                model=settings.openai.image_model,
                agent=self.name,
                task_id=task_code,
            )
            total_cost += image_cost

        return {
            "success": True,
            "result": {
                "prompt": optimized_prompt,
                "image_path": image_path or "画像生成APIが設定されていません",
                "description": description,
            },
            "cost_yen": total_cost,
        }

    async def _call_image_api(self, prompt: str, task_code: str) -> Optional[str]:
        """画像生成API呼び出し（DALL-E 3 or fal.ai）"""
        # DALL-E 3
        if settings.openai.api_key and settings.openai.api_key != "YOUR_OPENAI_API_KEY":
            try:
                from openai import AsyncOpenAI

                client = AsyncOpenAI(api_key=settings.openai.api_key)
                response = await client.images.generate(
                    model=settings.openai.image_model,
                    prompt=prompt,
                    size="1024x1024",
                    quality="standard",
                    n=1,
                )

                image_url = response.data[0].url
                # 画像をダウンロード・保存
                filename = f"{task_code}_{uuid.uuid4().hex[:8]}.png"
                filepath = os.path.join(IMAGE_OUTPUT_DIR, filename)

                import httpx
                async with httpx.AsyncClient() as http_client:
                    img_response = await http_client.get(image_url)
                    with open(filepath, "wb") as f:
                        f.write(img_response.content)

                logger.info(f"画像生成・保存完了: {filepath}")
                return filepath

            except Exception as e:
                logger.warning(f"DALL-E 3 エラー: {e}")

        # fal.ai フォールバック
        if settings.image_gen.fal_key and settings.image_gen.fal_key != "YOUR_FAL_AI_KEY":
            try:
                import fal_client

                handler = await fal_client.submit_async(
                    "fal-ai/flux/schnell",
                    arguments={"prompt": prompt, "image_size": "landscape_4_3"},
                )
                result = await handler.get()

                if result and "images" in result and result["images"]:
                    image_url = result["images"][0]["url"]
                    filename = f"{task_code}_{uuid.uuid4().hex[:8]}.png"
                    filepath = os.path.join(IMAGE_OUTPUT_DIR, filename)

                    import httpx
                    async with httpx.AsyncClient() as http_client:
                        img_response = await http_client.get(image_url)
                        with open(filepath, "wb") as f:
                            f.write(img_response.content)

                    logger.info(f"画像生成・保存完了 (fal.ai): {filepath}")
                    return filepath

            except Exception as e:
                logger.warning(f"fal.ai エラー: {e}")

        logger.info("画像生成APIが未設定 - プロンプトのみを返却")
        return None

    async def _meeting_design(self, task_code: str, payload: dict) -> dict:
        """会議用デザイン案提出"""
        topic = payload.get("topic", "")

        result = await self.call_llm(
            prompt=f"""AI社内会議のため、以下のテーマに対応する画像コンセプトを3つ提案してください。

テーマ: {topic}

各コンセプト:
- コンセプト名
- ビジュアルイメージの説明
- 画像生成プロンプト（英語）
- 推奨サイズ・フォーマット
- 使用するプラットフォーム""",
            system_prompt="あなたはSNSマーケティング専門のビジュアルデザイナーです。",
            tier=LLMTier.DEFAULT,
        )

        return {
            "success": True,
            "result": {"design_proposals": result.get("text", "")},
            "cost_yen": result.get("cost_yen", 0.0),
        }

    async def _create_image_prompt(self, task_code: str, payload: dict) -> dict:
        """画像生成プロンプトのみ作成"""
        description = payload.get("description", "")

        result = await self.call_llm(
            prompt=f"以下の説明から最適な画像生成プロンプトを英語で作成してください: {description}",
            system_prompt="あなたは画像生成のプロンプトエンジニアです。",
            tier=LLMTier.DEFAULT,
        )

        return {
            "success": True,
            "result": {"prompt": result.get("text", "")},
            "cost_yen": result.get("cost_yen", 0.0),
        }


# エージェントインスタンス
design_agent = DesignAgent()
