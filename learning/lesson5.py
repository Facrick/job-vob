salaries = [50000, 90000, 150000]

for salary in salaries:
    if salary >= 120000:
        print(f"{salary} -", "Высокая")
    elif salary >= 70000:
        print(f"{salary} -", "Средняя")
    else:
        print(f"{salary} -", "Низкая")
    