from app.connectors.contacts import GoogleContactsConnector


if __name__ == "__main__":
    connector = GoogleContactsConnector()
    print(connector.healthcheck())
    contacts = connector.list_contacts(page_size=50)
    print(f"contacts: {len(contacts)}")
    for contact in contacts[:10]:
        print(
            contact.get("display_name"),
            contact.get("emails"),
            contact.get("organization"),
        )
