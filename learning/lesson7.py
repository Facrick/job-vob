def salary_category(salary):
    if salary >= 120000:
        return "Высокая"
    elif salary >= 70000:
        return "Средняя"
    else:
        return "Низкая"

salaries = [50000, 90000, 150000]

for salary in salaries:
    print(f"{salary} - ", salary_category(salary))