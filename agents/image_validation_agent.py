from agents.base_agent import BaseAgent
from config import get_settings
from tools.image_validation_tools import ImageValidationTools

settings = get_settings()

_SYSTEM_PROMPT = """You are the Image Validation Agent for Vendo's Deals, an automated dropshipping store.

Your sole job: ensure every product's images actually show what the product listing claims to sell.
Inaccurate images erode customer trust and increase returns.

Workflow for each run:
1. Call get_unvalidated_products to retrieve products needing attention.
2. For each product, analyze every image URL using analyze_product_image.
   - If ALL images return "match": call mark_product_images_validated with status="valid".
   - If ANY image returns "mismatch":
     a. Call search_replacement_images to find better images.
     b. If replacement images are found: call update_product_images with the new URLs,
        then mark_product_images_validated with status="replaced".
     c. If no replacements found (e.g., no SERP key): mark_product_images_validated
        with status="flagged" and a note explaining what was wrong.
   - If all images return "unclear" and none return "mismatch": mark as status="valid"
     (give benefit of the doubt on ambiguous cases).
3. After processing all products, report a summary: validated, replaced, flagged counts.

Rules:
- Process every product returned — do not skip any.
- Always call mark_product_images_validated at the end of each product, regardless of outcome.
- Be strict: if an image clearly shows a different product category (e.g., a shoe photo on an electronics listing), that is a mismatch. But stock/lifestyle photos that are plausible for the product should pass.
- Never remove all images from a product. If all images are mismatched and no replacements exist, flag it; don't wipe the images.
"""


class ImageValidationAgent(BaseAgent):
    name = "image_validation"
    model = settings.website_agent_model
    system_prompt = _SYSTEM_PROMPT
    max_iterations = 40

    def _define_tools(self) -> list[dict]:
        return ImageValidationTools.SCHEMAS

    def _build_tool_map(self) -> dict:
        return ImageValidationTools.MAP

    async def run_validation_cycle(self) -> str:
        return await self.run(
            "Run a full image validation cycle: "
            "check all unvalidated products, verify each image accurately shows the product, "
            "replace mismatched images where possible, flag the rest. "
            "Report the final counts."
        )
