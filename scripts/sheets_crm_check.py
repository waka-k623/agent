from app.connectors.sheets_crm import SheetsCRMConnector


def main() -> None:
    crm = SheetsCRMConnector()
    print("Health:", crm.healthcheck())
    if not crm.healthcheck().get("ok"):
        return

    crm.ensure_headers()
    leads = crm.list_leads()
    print(f"Leads: {len(leads)}")
    for lead in leads[:10]:
        print(lead)


if __name__ == "__main__":
    main()
