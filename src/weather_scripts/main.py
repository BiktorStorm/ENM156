from find_data import find_dataa

# Add or remove SMHI parameter IDs and descriptions here anytime:
PARAMETERS = {
    1: "Lufttemperatur (momentanvärde, timvis, °C)",
    4: "Vindhastighet (10-min medelvärde, timvis, m/s)",
    16: "Total molnmängd (momentanvärde, timvis, mm)",
}

def select_parameter():
    print("Available SMHI parameters:")
    for param_id, desc in PARAMETERS.items():
        print(f"  [{param_id}] {desc}")

    while True:
        choice = input("\nEnter parameter ID: ").strip()
        print("")
        if choice.isdigit() and int(choice) in PARAMETERS:
            return int(choice)
        print(f"Invalid choice. Please enter one of: {list(PARAMETERS.keys())}")

if __name__ == "__main__":
    print("")
    selected_param = select_parameter()
    df = find_dataa(selected_param)
