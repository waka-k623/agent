from app.connectors.gmail import GmailConnector


def main() -> None:
    gmail = GmailConnector()

    print("Healthcheck:")
    print(gmail.healthcheck())

    print("\nRecent inbox messages:")
    for message in gmail.list_messages(query="in:inbox", max_results=5):
        print("-" * 60)
        print(f"From: {message['from']}")
        print(f"Subject: {message['subject']}")
        print(f"Date: {message['date']}")
        print(f"Snippet: {message['snippet']}")


if __name__ == "__main__":
    main()
