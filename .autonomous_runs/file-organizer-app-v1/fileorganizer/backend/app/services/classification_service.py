"""
Classification Service - LLM-based document classification
"""
from openai import OpenAI
from app.core.config import settings
from app.models.category import Category
from typing import Tuple, List
import json


class ClassificationService:
    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)

    def classify_document(
        self,
        document_text: str,
        categories: List[Category]
    ) -> Tuple[int, float]:
        """
        Classify document using GPT-4 with few-shot learning
        Returns: (category_id, confidence)
        """
        if not document_text or not categories:
            raise ValueError("Document text and categories required")

        # Build few-shot prompt
        prompt = self._build_classification_prompt(document_text, categories)

        try:
            response = self.client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a document classification expert. Classify documents into the most appropriate category based on their content."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.3,  # Low temperature for consistent classification
                max_tokens=200
            )

            result_text = response.choices[0].message.content.strip()

            # Parse response (expected format: "Category: <name>, Confidence: <0-100>")
            category_id, confidence = self._parse_classification_result(
                result_text,
                categories
            )

            return category_id, confidence

        except Exception as e:
            raise Exception(f"Classification failed: {str(e)}")

    def _build_classification_prompt(
        self,
        document_text: str,
        categories: List[Category]
    ) -> str:
        """Build few-shot classification prompt"""
        prompt_parts = [
            "Classify the following document into ONE of these categories:\n"
        ]

        # Add categories with examples
        for cat in categories:
            prompt_parts.append(f"\nCategory: {cat.name}")
            prompt_parts.append(f"Description: {cat.description or 'No description'}")

            # Add examples if available
            if cat.example_documents:
                try:
                    examples = json.loads(cat.example_documents) if isinstance(cat.example_documents, str) else cat.example_documents
                    prompt_parts.append("Examples:")
                    for ex in examples[:3]:  # Limit to 3 examples
                        prompt_parts.append(f"  - {ex}")
                except:
                    pass

        # Add document text (truncate if too long)
        max_text_length = 2000
        truncated_text = document_text[:max_text_length]
        if len(document_text) > max_text_length:
            truncated_text += "\n[... text truncated ...]"

        prompt_parts.append(f"\n\nDocument to classify:\n{truncated_text}")

        prompt_parts.append(
            "\n\nRespond with ONLY the category name and confidence (0-100)."
            "\nFormat: Category: <name>, Confidence: <score>"
        )

        return "\n".join(prompt_parts)

    def _parse_classification_result(
        self,
        result_text: str,
        categories: List[Category]
    ) -> Tuple[int, float]:
        """Parse LLM classification response"""
        try:
            # Expected format: "Category: Income, Confidence: 85"
            parts = result_text.split(",")

            # Extract category name
            category_part = parts[0].replace("Category:", "").strip()

            # Find matching category
            matched_category = None
            for cat in categories:
                if cat.name.lower() == category_part.lower():
                    matched_category = cat
                    break

            if not matched_category:
                # Fallback: return first category with low confidence
                return categories[0].id, 45.0

            # Extract confidence
            confidence = 50.0  # Default
            if len(parts) > 1:
                confidence_part = parts[1].replace("Confidence:", "").strip()
                try:
                    confidence = float(confidence_part)
                except:
                    confidence = 50.0

            return matched_category.id, min(max(confidence, 0.0), 100.0)

        except Exception as e:
            # Fallback: return first category with low confidence
            return categories[0].id, 45.0
