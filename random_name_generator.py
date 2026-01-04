import csv
import random

def set_values():
    firstnames = ["John", "Alex", "Katie", "Bob", "Joe", "Jim", "Xander", "Sarah", "George", "Abby", "Troy", "Sadie"]
    lastnames = ["Davis", "Donner", "Fisher", "Andrews", "Jones", "Smith"]
    data = []
    for i in range(random.randint(30,80)):
        data.append([firstnames[random.randint(0, len(firstnames)-1)], lastnames[random.randint(0, len(lastnames)-1)], random.randint(1, 7)])
    with open("data.csv", 'w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(["first_name", "last_name", "table"])
        writer.writerows(data)