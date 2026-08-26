from app.connectors.google_calendar import GoogleCalendarConnector
from app.services.calendar_sales import analyze_calendar_for_sales


if __name__ == "__main__":
    connector = GoogleCalendarConnector()
    print(connector.healthcheck())
    print()
    print(analyze_calendar_for_sales(
        "今週の営業予定を確認して、商談候補時間とフォローに良い時間帯を教えてください。",
        connector=connector,
        days=5,
    ))
