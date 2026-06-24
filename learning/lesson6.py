vacancy = {
    "title": "QA Engineer",
    "company": "Спикс",
    "salary_max": 90000
}

print(f"Вакансия: {vacancy['title']}")
print(f"Опыт: {vacancy.get('experience')}")

for key, value in vacancy.items():
    print(f"{key}: {value}")