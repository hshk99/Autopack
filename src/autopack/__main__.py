"""Main entry point for the Autopack Framework."""

from .document_classifier_canada import CanadaDocumentClassifier


def main():
    """Main function to demonstrate the Canada document classifier."""
    sample_text = """
    This is a sample document containing a CRA tax form.
    The date of issue is 2023-03-15 and the postal code is K1A 0B1.
    """

    classifier = CanadaDocumentClassifier()
    doc_type = classifier.classify_document(sample_text)
    date = classifier.extract_canadian_date(sample_text)
    postal_code = classifier.extract_canadian_postal_code(sample_text)

    print(f"Document Type: {doc_type}, Date: {date}, Postal Code: {postal_code}")


if __name__ == "__main__":
    main()
