import streamlit as st
import pandas as pd
import boto3
import uuid
import json
import time
import secrets
import csv
import io
import qrcode
# from PIL import Image
from difflib import SequenceMatcher
import time

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

# -----------------------
# CONFIG
# -----------------------
BASE_URL = "https://table-finder.streamlit.app"  # replace with your deployed URL
BUCKET = st.secrets["R2_BUCKET"]

# -----------------------
# R2 CLIENT
# -----------------------
s3 = boto3.client(
    "s3",
    endpoint_url=f"https://{st.secrets['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
    aws_access_key_id=st.secrets["R2_ACCESS_KEY_ID"],
    aws_secret_access_key=st.secrets["R2_SECRET_ACCESS_KEY"],
    region_name="auto",
)

# -----------------------
# HELPERS
# -----------------------
def r2_key(event_id, name):
    return f"events/{event_id}/{name}"

def r2_exists(key):
    try:
        s3.head_object(Bucket=BUCKET, Key=key)
        return True
    except:
        return False

def r2_delete_event(event_id):
    objs = s3.list_objects_v2(Bucket=BUCKET, Prefix=f"events/{event_id}/")
    if "Contents" in objs:
        s3.delete_objects(
            Bucket=BUCKET,
            Delete={"Objects": [{"Key": o["Key"]} for o in objs["Contents"]]},
        )

def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def find_by_last_name_fuzzy(last_name, threshold=0.75, limit=5):
    results = []
    for g in guests:
        score = similarity(last_name, g["last_name"])
        if score >= threshold:
            results.append((score, g))
    results.sort(reverse=True, key=lambda x: x[0])
    return [g for _, g in results[:limit]]

def find_by_first_name_fuzzy(first_name, threshold=0.75, limit=5):
    results = []
    for g in guests:
        score = similarity(first_name, g["first_name"])
        if score >= threshold:
            results.append((score, g))
    results.sort(reverse=True, key=lambda x: x[0])
    return [g for _, g in results[:limit]]

# -----------------------
# QUERY PARAMS
# -----------------------
event_id = st.query_params.get("event")
token = st.query_params.get("token")
if isinstance(event_id, list): event_id = event_id[0]
if isinstance(token, list): token = token[0]

st.title("TableFinder")
st.caption("by Sam Davisson")

# ============================================================
# CREATE EVENT
# ============================================================
if not event_id:
    st.header("Home")

    create, adminpage, help = st.tabs(["Create an event", "Admin Login", "Instructions"], default="Instructions")
    with help:
        st.header("Instructions")
        st.markdown("""
        **Welcome to TableFinder!**  

        Here's how to use the app:

        1. **Create an Event**
           - Go to the 'Create an Event' tab.
           - Enter your event title.
           - Upload a CSV file with your guests. The CSV file should include first name, last name, and table columns (any column names are fine; you will map them).
           - Click 'Create Event' to generate your event.
           - A QR code and guest/admin links will be generated automatically.
           - Download your Admin File to recover the event later if needed.

        2. **Admin Page**
           - Use the admin link or upload your Admin File in the 'Admin Login' tab.
           - Edit guest lists, tables, or event title.
           - Download the guest CSV file or QR code at any time.
           - Delete the event if needed (permanent).

        3. **Guest Lookup**
           - Guests can use the QR code or guest link.
           - Search by first or last name.
           - See their table assignments.

        **Tips:**
        - Always keep your Admin File safe.
        - Column mapping is remembered if you upload a new CSV file later.
        - Tables can be numbers or names (like "A", "B", "Family Table").
        """)
    with adminpage:
        uploaded_safe = st.file_uploader("Upload admin recover file", type="json")

        if uploaded_safe:
            safe_data = json.load(uploaded_safe)
            st.query_params["event"] = safe_data["event_id"]
            st.query_params["token"] = safe_data["creator_token"]
            st.rerun()
    with create:
        title = st.text_input("Event title")
        uploaded = st.file_uploader("Upload guest list", type="csv")
        "Or"
        blank = st.checkbox("Create a blank list")

        if blank:
            df = pd.DataFrame(columns=["first_name", "last_name", "table"])
            # if st.button("Create Event"):
            #     event_id = uuid.uuid4().hex[:6]
            #     creator_token = secrets.token_hex(4)
            #
            #     # Save CSV to R2
            #     s3.put_object(
            #         Bucket=BUCKET,
            #         Key=r2_key(event_id, "guests.csv"),
            #         Body=df.to_csv(index=False),
            #     )
            #
            #     # Save metadata with column mapping
            #     meta = {
            #         "title": title or "Untitled Event",
            #         "created": time.time(),
            #         "creator_token": creator_token,
            #         "column_mapping": {
            #             "first_name": "first_name",
            #             "last_name": "last_name",
            #             "table": "table"
            #         },
            #         "table_prefix": "Table"
            #     }
            #     s3.put_object(
            #         Bucket=BUCKET,
            #         Key=r2_key(event_id, "meta.json"),
            #         Body=json.dumps(meta),
            #     )
            #
            #     # Generate URLs
            #     guest_url = f"{BASE_URL}/?event={event_id}"
            #     admin_url = f"{BASE_URL}/?event={event_id}&token={creator_token}"
            #
            #     # QR code
            #     qr = qrcode.make(guest_url)
            #     buf = io.BytesIO()
            #     qr.save(buf, format="PNG")
            #     buf.seek(0)
            #
            #     # Display QR and links
            #     st.success("Event created!")
            #     st.image(buf, width=250)
            #     st.download_button(
            #         label="Download QR code",
            #         data=buf.getvalue(),
            #         file_name="qr.png",
            #         mime="image/png"
            #     )
            #     st.markdown(f"**Guest link:** {guest_url}")
            #     st.markdown(f"**Admin link:** {admin_url}")
            #
            #     # Generate safe file
            #     safe_file = {
            #         "event_id": event_id,
            #         "creator_token": creator_token,
            #         "title": meta["title"],
            #         "table_prefix": meta["table_prefix"]
            #     }
            #     safe_bytes = json.dumps(safe_file, indent=2).encode("utf-8")
            #     st.download_button(
            #         label="Download Admin File",
            #         data=safe_bytes,
            #         file_name=f"event_{event_id}_admin.json",
            #         mime="application/json"
            #     )
            #
            #     # Redirect to admin page
            #     st.query_params["event"] = event_id
            #     st.query_params["token"] = creator_token
            #     st.rerun()

        if blank or uploaded:
            # -----------------------
            # Map columns
            # -----------------------
            if uploaded:
                df = pd.read_csv(uploaded)
                st.write("Detected columns:", list(df.columns))
                first_col = st.selectbox("Select the first name column:", df.columns, index=0)
                last_col = st.selectbox("Select the last name column:", df.columns, index=1)
                table_col = st.selectbox("Select the table column:", df.columns, index=2)

                # Rename columns internally
                df = df.rename(columns={
                    first_col: "first_name",
                    last_col: "last_name",
                    table_col: "table"
                })

                if "table" in df.columns:
                    df["table"] = df["table"].astype(str)
                df = df.reset_index(drop=True)

            if st.button("Create Event"):
                event_id = uuid.uuid4().hex[:6]
                creator_token = secrets.token_hex(4)

                # Save CSV to R2
                s3.put_object(
                    Bucket=BUCKET,
                    Key=r2_key(event_id, "guests.csv"),
                    Body=df.to_csv(index=False),
                )

                # Save metadata with column mapping
                if uploaded:
                    meta = {
                        "title": title or "Untitled Event",
                        "created": time.time(),
                        "creator_token": creator_token,
                        "column_mapping": {
                            "first_name": first_col,
                            "last_name": last_col,
                            "table": table_col
                        },
                        "table_prefix": "Table"
                    }
                else:
                    meta = {
                                "title": title or "Untitled Event",
                                "created": time.time(),
                                "creator_token": creator_token,
                                "column_mapping": {
                                    "first_name": "first_name",
                                    "last_name": "last_name",
                                    "table": "table"
                                },
                                "table_prefix": "Table"
                            }
                s3.put_object(
                    Bucket=BUCKET,
                    Key=r2_key(event_id, "meta.json"),
                    Body=json.dumps(meta),
                )

                # Generate URLs
                guest_url = f"{BASE_URL}/?event={event_id}"
                admin_url = f"{BASE_URL}/?event={event_id}&token={creator_token}"

                # QR code
                qr = qrcode.make(guest_url)
                buf = io.BytesIO()
                qr.save(buf, format="PNG")
                buf.seek(0)

                # Display QR and links
                st.success("Event created!")
                st.image(buf, width=250)
                st.download_button(
                    label="Download QR code",
                    data=buf.getvalue(),
                    file_name="qr.png",
                    mime="image/png"
                )
                st.markdown(f"**Guest link:** {guest_url}")
                st.markdown(f"**Admin link:** {admin_url}")

                # Generate safe file
                safe_file = {
                    "event_id": event_id,
                    "creator_token": creator_token,
                    "title": meta["title"],
                    "table_prefix": meta["table_prefix"]
                }
                safe_bytes = json.dumps(safe_file, indent=2).encode("utf-8")
                st.download_button(
                    label="Download Admin File",
                    data=safe_bytes,
                    file_name=f"event_{event_id}_admin.json",
                    mime="application/json"
                )

                # Redirect to admin page
                st.query_params["event"] = event_id
                st.query_params["token"] = creator_token
                st.rerun()

# ============================================================
# LOAD EVENT
# ============================================================
csv_key = r2_key(event_id, "guests.csv")
meta_key = r2_key(event_id, "meta.json")

if not r2_exists(csv_key) or not r2_exists(meta_key):
    st.stop()

meta = json.loads(s3.get_object(Bucket=BUCKET, Key=meta_key)["Body"].read())
is_admin = token == meta["creator_token"]

st.header(meta["title"])
st.caption(f"Event ID: {event_id}")

# ============================================================
# ADMIN PAGE
# ============================================================
if is_admin:
    st.warning("Creator/Admin Page")

    # Download admin safe file

    "Use this to recover this page if you accidentally close it"
    safe_file = {
        "event_id": event_id,
        "creator_token": token,
        "title": meta.get("title", "Untitled Event"),
        "table_prefix": meta.get("table_prefix", "Table")
    }
    safe_bytes = json.dumps(safe_file, indent=2).encode("utf-8")
    st.download_button(
        label="Download Admin Recover File",
        data=safe_bytes,
        file_name=f"event_{event_id}_admin.json",
        mime="application/json"
    )


    share = st.expander("Share event")
    with share:
        # Guest URL & QR
        guest_url = f"{BASE_URL}/?event={event_id}"
        qr = qrcode.make(guest_url)
        buf = io.BytesIO()
        qr.save(buf, format="PNG")
        buf.seek(0)
        st.image(buf, width=250)
        st.download_button(
            label="Download QR code",
            data=buf.getvalue(),
            file_name="qr.png",
            mime="image/png"
        )
        "Guest Link"
        st.code(guest_url, language="txt")

    event_data = st.expander("Edit event")
    with event_data:
        # Edit event title
        new_title = st.text_input("Edit event title:", value=meta["title"])
        if new_title != meta["title"]:
            meta["title"] = new_title
            s3.put_object(
                Bucket=BUCKET,
                Key=meta_key,
                Body=json.dumps(meta),
            )
            st.success("Event title updated!")
            st.rerun()

        # Load CSV
        if "df" not in st.session_state:
            csv_data = s3.get_object(Bucket=BUCKET, Key=csv_key)["Body"].read()
            df = pd.read_csv(io.BytesIO(csv_data))
            if "table" in df.columns:
                df["table"] = df["table"].astype(str)
            df = df.reset_index(drop=True)
            st.session_state.df = df

        # Map internal to friendly column headers
        friendly_cols = {"first_name": "First Name", "last_name": "Last Name", "table": "Table"}
        df_friendly = st.session_state.df.rename(columns=friendly_cols)

        # -----------------------
        # Apply table prefix in admin view
        # -----------------------
        table_prefix = meta.get("table_prefix", "Table")
        # df_friendly["Table"] = df_friendly["Table"].apply(lambda x: f"{table_prefix} {x}" if x else "")

        # Editable guest list with table prefix
        st.caption(
            "You can enter full table names (e.g. 'Round Table') "
            "or just numbers (e.g. '2'). "
            "The prefix is only added for numbers."
        )
        df_friendly = df_friendly.reset_index(drop=True)
        edited_friendly = st.data_editor(
            df_friendly,
            num_rows="dynamic",
            hide_index=True,
            key="guest_editor"
        )
        if st.button("Save changes"):
            saving = st.toast("Saving...", icon="spinner")
            edited_internal = edited_friendly.rename(
                columns={v: k for k, v in friendly_cols.items()}
            )
            edited_internal = edited_internal.fillna("").astype(str)
            edited_internal = edited_internal.reset_index(drop=True)
            s3.put_object(
                Bucket=BUCKET,
                Key=csv_key,
                Body=edited_internal.to_csv(index=False),
            )

            st.session_state.df = edited_internal
            time.sleep(0.5)
            saving.toast("Saved!", icon="✅", duration=2)
        if "uploadedval" not in st.session_state:
            st.session_state.uploadedval = 0
            print("hello")
        # Replace CSV while remembering column mapping
        uploaded_replace = st.file_uploader("Or upload a new CSV to replace guest list", type="csv", key=str(st.session_state.uploadedval))
        if uploaded_replace:
            df_new = pd.read_csv(uploaded_replace)
            st.write("Detected columns:", list(df_new.columns))
            first_col = st.selectbox("Select the first name column:", df_new.columns, index=0)
            last_col = st.selectbox("Select the last name column:", df_new.columns, index=1)
            table_col = st.selectbox("Select the table column:", df_new.columns, index=2)

            if st.button("Update"):
                meta["column_mapping"] = {
                    "first_name": first_col,
                    "last_name": last_col,
                    "table": table_col
                }
                # Rename columns internally
                df_new = df_new.rename(columns={
                    first_col: "first_name",
                    last_col: "last_name",
                    table_col: "table"
                })

                if "table" in df_new.columns:
                    df_new["table"] = df_new["table"].astype(str)
                df_new = df_new.reset_index(drop=True)
                column_mapping = meta.get("column_mapping", {"first_name":"first_name","last_name":"last_name","table":"table"})
                if "table" in df_new.columns:
                    df_new["table"] = df_new["table"].astype(str)
                df_new = df_new.reset_index(drop=True)

                s3.put_object(
                    Bucket=BUCKET,
                    Key=csv_key,
                    Body=df_new.to_csv(index=False)
                )
                s3.put_object(
                    Bucket=BUCKET,
                    Key=meta_key,
                    Body=json.dumps(meta),
                )
                st.session_state.df = df_new
                st.toast("Guest list replaced")
                st.session_state.uploadedval += 1
                # uploaded_replace = st.file_uploader("Or upload a new CSV to replace guest list", type="csv", key="newfileuploader")
                st.rerun()

        # -----------------------
        # Edit table prefix
        # -----------------------
        "Use this to edit what the guests see before their table. For example, instead of \"Table 1\", they would see \"Room 1\" if it was set to \"Room\""
        new_table_prefix = st.text_input("Edit table prefix:", value=meta.get("table_prefix", "Table"))
        if new_table_prefix != meta["table_prefix"]:
            meta["table_prefix"] = new_table_prefix
            s3.put_object(
                Bucket=BUCKET,
                Key=meta_key,
                Body=json.dumps(meta),
            )
            st.success("Table prefix updated!")
            st.rerun()

    # Delete event
    st.divider()
    delete = st.expander("Delete Event")
    with delete:
        st.error("**This is permanent and cannot be undone**")
        confirm = st.text_input("Type the name of your event to confirm deletion", key="open_delete_menu")
        if confirm == meta["title"]:
            r2_delete_event(event_id)
            st.success("Event deleted")
            del st.query_params["event"]
            del st.query_params["token"]
            st.rerun()
    st.stop()

# ============================================================
# GUEST LOOKUP
# ============================================================
csv_data = s3.get_object(Bucket=BUCKET, Key=csv_key)["Body"].read()
guests = list(csv.DictReader(io.StringIO(csv_data.decode())))
for g in guests:
    g["table"] = str(g.get("table", ""))

# Map internal to friendly column headers for display
friendly_cols = {"first_name": "First Name", "last_name": "Last Name", "table": "Table"}

search_by_first = st.toggle("Search by first name")
if "name_val" not in st.session_state:
    st.session_state.name_val = ""

# Get table prefix from metadata
table_prefix = meta.get("table_prefix", "Table")

if search_by_first:
    name_input = st.text_input(
        "Your first name:",
        value=st.session_state.name_val,
        key="first_name_input"
    )
    matches = find_by_first_name_fuzzy(name_input, 0.7) if len(name_input) >= 2 else []
else:
    name_input = st.text_input(
        "Your last name:",
        value=st.session_state.name_val,
        key="last_name_input"
    )
    matches = find_by_last_name_fuzzy(name_input, 0.7) if len(name_input) >= 2 else []

st.session_state.name_val = name_input

# -----------------------
# Display guest results with table prefix
# -----------------------
if name_input:
    if matches:
        for guest in matches:
            raw_table = guest["table"].strip()

            if raw_table:
                if table_prefix and raw_table.isdigit():
                    display_table = f"{table_prefix} {raw_table}"
                else:
                    display_table = raw_table
            else:
                display_table = ""

            st.write(
                f"**{guest['first_name']} {guest['last_name']}** — {display_table}"
            )
    else:
        st.warning("No matches found.")