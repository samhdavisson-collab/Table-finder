import streamlit as st
import csv
import random_name_generator

st.markdown(
    """
<style>
body {
    overflow-y: scroll; /* Always show the vertical scrollbar */
}
</style>
""",
    unsafe_allow_html=True,
)
st.title("TableFinder")
"by Sam Davisson"
if "name_val" not in st.session_state:
     st.session_state.name_val = ""
     random_name_generator.set_values()
guests = []
with open('data.csv', mode='r', newline='', encoding='utf-8') as file:
    reader = csv.DictReader(file)
    for row in reader:
        guests.append(row)
        # Or print the entire dictionary row
        # print(row)


def find_by_last_name(last_name):
    return [g for g in guests if last_name.lower() in g["last_name"].lower() ]
def find_by_first_name(first_name):
    return [g for g in guests if first_name.lower() in g["first_name"].lower() ]


# selectbox = "Search by " + st.selectbox("", ["first name", "last name"], width=200)
selectbox = st.toggle("Search by first name")


if not selectbox:# == "Search by last name":
    textinput = st.text_input("Your last name:", value=st.session_state.name_val)
    matches = find_by_last_name(textinput)
    st.session_state.name_val = textinput
    for guest in matches:
        st.write(f"{guest['first_name']} {guest['last_name']} - {guest['table']}")
else:
    textinput = st.text_input("Your first name:", value=st.session_state.name_val)
    matches = find_by_first_name(textinput)
    st.session_state.name_val = textinput
    for guest in matches:
        st.write(f"{guest['first_name']} {guest['last_name']} - {guest['table']}")