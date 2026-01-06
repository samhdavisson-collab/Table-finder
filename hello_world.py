import streamlit as st
import csv
import os
import uuid
import json
import qrcode
from PIL import Image
import io
import secrets
import time
import pandas as pd

# -----------------------
# Setup
# -----------------------
EVENTS_DIR = "events"
os.makedirs(EVENTS_DIR, exist_ok=True)

# For local testing; replace with deployed URL when live
BASE_URL = "http://localhost:8501"

# -----------------------
# Get event_id and token from URL query parameters
# -----------------------
event_id = st.query_params.get("event")
if isinstance(event_id, list):
    event_id = event_id[0]

token_param = st.query_params.get("token")
if isinstance(token_param, list):
    token_param = token_param[0]

st.markdown(
    """
    <style>
    body {
        overflow-y: scroll;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("TableFinder")
st.caption("by Sam Davisson")

# -----------------------
# CREATE EVENT MODE
# -----------------------
if not event_id:
    st.header("Create an Event")

    # Event title input
    event_title_input = st.text_input(
        "Event title",
        placeholder="",
        key="event_title_input"
    )

    # CSV uploader
    uploaded = st.file_uploader(
        "Upload your guest list (CSV)",
        type="csv"
    )

    if uploaded:
        # Generate unique event ID
        event_id = uuid.uuid4().hex[:6]

        # Generate creator token
        creator_token = secrets.token_hex(4)

        # Save CSV
        csv_path = os.path.join(EVENTS_DIR, f"{event_id}.csv")
        with open(csv_path, "wb") as f:
            f.write(uploaded.getbuffer())

        # Ensure 'table' column is string
        df = pd.read_csv(csv_path)
        if "table" in df.columns:
            df["table"] = df["table"].astype(str)
            df.to_csv(csv_path, index=False)

        # Save metadata (title, created timestamp, creator token)
        meta = {
            "title": event_title_input.strip() or "Untitled Event",
            "created": time.time(),
            "creator_token": creator_token
        }
        meta_path = os.path.join(EVENTS_DIR, f"{event_id}.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f)

        st.success("Event created!")

        # Generate full URLs
        guest_url = f"{BASE_URL}/?event={event_id}"
        admin_url = f"{BASE_URL}/?event={event_id}&token={creator_token}"

        # -----------------------
        # Generate QR code for guests
        # -----------------------
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(guest_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)

        st.markdown("### Guest Lookup Ready")
        st.markdown("**Scan this QR code to access the guest lookup:**")
        st.image(buf, caption="Scan QR code", width=250)
        st.download_button(
            label="Download QR code",
            data=buf.getvalue(),
            file_name=f"event_{event_id}_qr.png",
            mime="image/png"
        )
        st.markdown(f"[Or click here to open]({guest_url})")
        st.markdown(f"**Creator/admin page:** [Click here]({admin_url})")

    st.stop()  # Stop execution so guest lookup code doesn't run

# -----------------------
# LOAD EVENT
# -----------------------
csv_path = os.path.join(EVENTS_DIR, f"{event_id}.csv")
meta_path = os.path.join(EVENTS_DIR, f"{event_id}.json")

if not os.path.exists(csv_path) or not os.path.exists(meta_path):
    st.error("Event not found.")
    st.stop()

with open(meta_path, "r", encoding="utf-8") as f:
    meta = json.load(f)

event_title = meta.get("title", "Untitled Event")
creator_token = meta.get("creator_token")
is_creator = token_param == creator_token

# -----------------------
# DISPLAY HEADER
# -----------------------
st.header(event_title)
st.caption(f"Event ID: {event_id}")

# -----------------------
# CREATOR/ADMIN DASHBOARD
# -----------------------
if is_creator:
    st.warning("You are viewing the creator/admin page for this event.")

    # Edit event title
    new_title = st.text_input("Edit event title:", value=event_title, key="edit_event_title")
    if new_title != event_title:
        meta["title"] = new_title
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f)
        st.success("Event title updated!")
        event_title = new_title

    # Load guest list as DataFrame
    df = pd.read_csv(csv_path)
    if "table" in df.columns:
        df["table"] = df["table"].astype(str)

    # Editable guest list
    st.markdown("### Edit Guest List")
    edited_df = st.data_editor(df, num_rows="dynamic", key="edit_guest_list")

    # Save changes if edited
    if not edited_df.equals(df):
        if "table" in edited_df.columns:
            edited_df["table"] = edited_df["table"].astype(str)
        edited_df.to_csv(csv_path, index=False)
        st.success("Guest list updated!")

    # Replace CSV upload
    uploaded = st.file_uploader("Or upload a new CSV to replace guest list", type="csv", key="replace_csv")
    if uploaded:
        with open(csv_path, "wb") as f:
            f.write(uploaded.getbuffer())
        df = pd.read_csv(csv_path)
        if "table" in df.columns:
            df["table"] = df["table"].astype(str)
        st.success("Guest list replaced!")

    # QR code for guests
    guest_url = f"{BASE_URL}/?event={event_id}"
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(guest_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    st.markdown("### QR Code for Guests")
    st.image(buf, caption="Scan QR code", width=250)
    st.download_button(
        label="Download QR code",
        data=buf.getvalue(),
        file_name=f"event_{event_id}_qr.png",
        mime="image/png"
    )

    # Download CSV
    with open(csv_path, "rb") as f:
        csv_bytes = f.read()
    st.download_button(
        label="Download guest list CSV",
        data=csv_bytes,
        file_name=f"event_{event_id}_guests.csv",
        mime="text/csv"
    )

    # Delete event
    confirm = st.checkbox("Confirm deletion of this event permanently")
    if confirm and st.button("Delete event"):
        if os.path.exists(csv_path):
            os.remove(csv_path)
        if os.path.exists(meta_path):
            os.remove(meta_path)
        st.success("Event deleted!")
        st.stop()

# -----------------------
# GUEST LOOKUP
# -----------------------
with open(csv_path, mode="r", newline="", encoding="utf-8") as file:
    reader = csv.DictReader(file)
    guests = list(reader)
    # ensure table is string
    for g in guests:
        g["table"] = str(g.get("table", ""))

def find_by_last_name(last_name):
    return [g for g in guests if last_name.lower() in g["last_name"].lower()]

def find_by_first_name(first_name):
    return [g for g in guests if first_name.lower() in g["first_name"].lower()]

if "name_val" not in st.session_state:
    st.session_state.name_val = ""

search_by_first = st.checkbox("Search by first name")

if search_by_first:
    name_input = st.text_input(
        "Your first name:",
        value=st.session_state.name_val,
        key="first_name_input"
    )
    matches = find_by_first_name(name_input)
else:
    name_input = st.text_input(
        "Your last name:",
        value=st.session_state.name_val,
        key="last_name_input"
    )
    matches = find_by_last_name(name_input)

st.session_state.name_val = name_input

if name_input:
    if matches:
        for guest in matches[:5]:
            st.write(f"**{guest['first_name']} {guest['last_name']}** — Table {guest['table']}")
    else:
        st.warning("No matches found.")
