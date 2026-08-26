from pprint import pprint

from app.connectors.gmail import GmailConnector
from app.email_analysis import analyze_email


def main() -> None:
    gmail = GmailConnector()
    messages = gmail.list_messages(query="in:inbox newer_than:14d", max_results=10)

    results = []
    for message in messages:
        analysis = analyze_email(message)
        results.append(
            {
                "email": {
                    "id": message.get("id"),
                    "from": message.get("from"),
                    "subject": message.get("subject"),
                    "date": message.get("date"),
                },
                "analysis": analysis,
            }
        )

    priority_order = {"high": 0, "medium": 1, "low": 2}
    results.sort(
        key=lambda item: (
            not item["analysis"].get("is_sales_related", False),
            priority_order.get(item["analysis"].get("priority", "low"), 9),
        )
    )

    pprint(results, sort_dicts=False)


if __name__ == "__main__":
    main()
