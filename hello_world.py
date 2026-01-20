import streamlit as st
import pandas as pd
import boto3
import uuid
import json
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
@st.cache_data(ttl=60)
def load_csv_from_r2(bucket, key):
    csv_bytes = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    df = pd.read_csv(io.BytesIO(csv_bytes))
    if "table" in df.columns:
        df["table"] = df["table"].astype(str)
    return df.reset_index(drop=True)


@st.cache_data(ttl=60)
def load_meta_from_r2(bucket, key):
    return json.loads(
        s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    )

def make_wifi_qr(ssid, password, security="WPA"):
    if not password:
        security = "nopass"

    wifi_str = f"WIFI:T:{security};S:{ssid};P:{password};;"
    qr = qrcode.make(wifi_str)

    buf = io.BytesIO()
    qr.save(buf, format="PNG")
    buf.seek(0)
    return buf

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

        Here's how to use this site:

        1. **Create an Event**
           - Go to the 'Create an Event' tab.
           - Enter your event title.
           - Upload a CSV file with your guests. The CSV file should include first name, last name, and table columns (any column names are fine; you will map them).
           - You can also click "Create a blank list" to create without uploading a CSV file.
           - Set a time for the event to get automatically deleted.
           - Map the columns so the names appear correctly.
           - Click 'Create Event' to generate your event.
           - *IMPORTANT: You will not be able to get back to the Admin Page without downloading the admin file.*

        2. **Admin Page**
           - Upload your Admin File in the 'Admin Login' tab if you lose the page.
           - Edit the guest list, event title, or deletion date.
           - Generate a QR code for the WiFi and guest lookup.
           - Download a guest list PDF to put up for guests who don't have phones.

        3. **Guest Lookup**
           - Use the QR code or guest link.
           - Search by first or last name.
           - See table assignments.

        **Tips:**
        - Always keep your Admin File safe.
        - Tables can be numbers or names (like "A", "B", "Family Table", "1").
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
            from datetime import date

            picked_date = st.date_input(
                "Automatically delete this event after:",
                value=date.today(),
                min_value=date.today()
            )

            if picked_date:# != delete_after_date:
                delete_after = picked_date.isoformat()
                st.toast(f"Event will be deleted after {picked_date}", icon="⏰")

            if st.button("Create Event"):
                event_id = uuid.uuid4().hex[:6]
                creator_token = secrets.token_hex(4)

                # Save CSV to R2
                s3.put_object(
                    Bucket=BUCKET,
                    Key=r2_key(event_id, "guests.csv"),
                    Body=df.to_csv(index=False),
                )
                load_csv_from_r2.clear()

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
                        "table_prefix": "Table",
                        "delete_after": delete_after
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
                                "table_prefix": "Table",
                                "delete_after": delete_after
                            }
                s3.put_object(
                    Bucket=BUCKET,
                    Key=r2_key(event_id, "meta.json"),
                    Body=json.dumps(meta),
                )
                load_meta_from_r2.clear()

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
    # st.error("Event does not exist", icon="⚠️")
    if event_id:
        st.query_params.clear()
        st.rerun()
    st.stop()

meta = load_meta_from_r2(BUCKET, meta_key)
is_admin = token == meta["creator_token"]

st.header(f"Creator/Admin page for \"{meta['title']}\" event")
st.caption(f"Event ID: {event_id}")

# ============================================================
# ADMIN PAGE
# ============================================================
if is_admin:
    # st.sidebar.title("Admin")
    #
    # if "admin_page" not in st.session_state:
    #     st.session_state.admin_page = "share"
    #
    # if st.sidebar.button("Share event"):
    #     st.session_state.admin_page = "share"
    #
    # if st.sidebar.button("Edit event"):
    #     st.session_state.admin_page = "edit"
    #
    # if st.sidebar.button("Wi-Fi QR"):
    #     st.session_state.admin_page = "wifi"
    #
    # if st.sidebar.button("Delete event"):
    #     st.session_state.admin_page = "delete"
    #st.warning("Creator/Admin Page")

    # Download admin safe file

    safe_file = {
        "event_id": event_id,
        "creator_token": token,
        "title": meta.get("title", "Untitled Event"),
        "table_prefix": meta.get("table_prefix", "Table")
    }
    safe_bytes = json.dumps(safe_file, indent=2).encode("utf-8")
    # st.divider()
    st.info("***IMPORTANT!*** Use this to recover if you close the tab")
    st.download_button(
        label="**Download Admin Recover File**",
        data=safe_bytes,
        file_name=f"{meta.get('title')}_admin.json",
        mime="application/json",
        type="primary",
        help="***Do this!***"
    )
    #st.warning("Use this to recover if you close the tab")
    st.divider()
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
        from datetime import date

        delete_after = meta.get("delete_after")  # stored as YYYY-MM-DD string
        delete_after_date = (
            date.fromisoformat(delete_after)
            if delete_after
            else None
        )

        picked_date = st.date_input(
            "Automatically delete this event after:",
            value=delete_after_date,
            min_value=date.today()
        )

        if picked_date != delete_after_date:
            meta["delete_after"] = picked_date.isoformat()
            s3.put_object(
                Bucket=BUCKET,
                Key=meta_key,
                Body=json.dumps(meta),
            )
            load_meta_from_r2.clear()

            st.toast(f"Event will be deleted after {picked_date}", icon="⏰")
        # Edit event title
        new_title = st.text_input("Edit event title:", value=meta["title"])
        if new_title != meta["title"]:
            meta["title"] = new_title
            s3.put_object(
                Bucket=BUCKET,
                Key=meta_key,
                Body=json.dumps(meta),
            )
            load_meta_from_r2.clear()
            st.toast("Event title updated!")
            st.rerun()

        # Load CSV
        if "df" not in st.session_state:
            df = load_csv_from_r2(BUCKET, csv_key)
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
            load_csv_from_r2.clear()

            st.session_state.df = edited_internal
            time.sleep(1)
            saving.toast("Saved!", icon="✅", duration=2)
        if "uploadedval" not in st.session_state:
            st.session_state.uploadedval = 0
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
                load_csv_from_r2.clear()
                load_meta_from_r2.clear()
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
            load_meta_from_r2.clear()
            st.success("Table prefix updated!")
            st.rerun()
    wifi_qr = st.expander("WiFi QR Code")
    with wifi_qr:
        # st.subheader("", help=
        # "Your Wi-Fi name and password are used only to generate the QR code. "
        # "They are never saved, logged, or stored."
        #              )
        st.caption("Your Wi-Fi information is used locally to generate the QR code."
        "It is never saved, logged, or stored.")
        ssid = st.text_input("Wi-Fi Network Name (SSID)")
        password = st.text_input("Wi-Fi Password", type="password")
        security = st.selectbox(
            "Security type",
            ["WPA", "WEP", "Open (no password)"]
        )

        if security == "Open (no password)":
            security = "nopass"

        if ssid:
            wifi_qr = make_wifi_qr(ssid, password, security)
            st.image(wifi_qr, width=250)
            st.download_button(
                "Download Wi-Fi QR code",
                data=wifi_qr.getvalue(),
                file_name="wifi_qr.png",
                mime="image/png"
            )
    printout = st.expander("Print Guest List")
    with printout:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas

        # Fetch CSV bytes from S3
        df = load_csv_from_r2(BUCKET, csv_key)
        if not df.empty:
            sort = st.radio("Sort By:", ["First Name", "Last Name", "None"])
            if sort == "First Name" or sort == "None":
                name_arrange = st.radio("Name Arrangement: ", [f"{df.iloc[0]['first_name']} {df.iloc[0]['last_name']}", f"{df.iloc[0]['last_name']}, {df.iloc[0]['first_name']}"])
            if sort == "Last Name":
                name_arrange = st.radio("Name Arrangement: ", [f"{df.iloc[0]['first_name']} {df.iloc[0]['last_name']}", f"{df.iloc[0]['last_name']}, {df.iloc[0]['first_name']}"], index=1)

            # CSV is already loaded in df
            if sort == "First Name":
                df_sorted = df.sort_values("first_name")  # sort alphabetically
            elif sort == "Last Name":
                df_sorted = df.sort_values("last_name")
            elif sort == "None":
                df_sorted = df

            guests_per_page = 9999999999999999999999999999
            pages = [df_sorted.iloc[i:i + guests_per_page] for i in range(0, len(df_sorted), guests_per_page)]

            pdf_buffer = io.BytesIO()
            c = canvas.Canvas(pdf_buffer, pagesize=letter)
            width, height = letter
            table_prefix = meta.get("table_prefix", "Table")
            # ----- Layout constants -----
            LEFT_X = 50
            TABLE_X = 260
            MAX_NAME_WIDTH = TABLE_X - LEFT_X - 10
            BOTTOM_MARGIN = 80

            page_number = 1

            for page in pages:
                last_letter = None

                # ----- Page header -----
                c.setFont("Helvetica-Bold", 20)
                c.drawCentredString(width / 2, height - 40, meta["title"])
                c.line(50, height - 60, width - 50, height - 60)

                y = height - 90  # start content below title

                for idx, row in page.iterrows():
                    # ----- Page overflow check -----
                    if y < BOTTOM_MARGIN:
                        c.setFont("Helvetica-Oblique", 8)
                        c.drawRightString(width - 20, 20, str(page_number))
                        c.drawString(50, 20, "Made with TableFinder")
                        c.showPage()
                        page_number += 1
                        last_letter = None

                        c.setFont("Helvetica-Bold", 20)
                        c.drawCentredString(width / 2, height - 40, meta["title"])
                        c.line(50, height - 60, width - 50, height - 60)
                        y = height - 90

                    # ----- Safe string conversion -----
                    first_name = str(row.get("first_name", "")).strip()
                    last_name = str(row.get("last_name", "")).strip()
                    table_raw = str(row.get("table", "")).strip()

                    # ----- Alphabet key -----
                    key_name = last_name if sort == "Last Name" else first_name
                    current_letter = key_name[:1].upper() if key_name else "#"

                    # ----- Alphabet header -----
                    if current_letter != last_letter:
                        if y < BOTTOM_MARGIN + 40:
                            c.showPage()
                            page_number += 1
                            last_letter = None
                            y = height - 90

                        c.setFont("Helvetica-Bold", 14)
                        c.drawString(LEFT_X, y, current_letter)
                        y -= 12
                        c.line(LEFT_X, y, width - 50, y)
                        y -= 18
                        last_letter = current_letter

                    # ----- Build display name -----
                    if name_arrange == f"{df.iloc[0]['first_name']} {df.iloc[0]['last_name']}":
                        name_text = f"{first_name} {last_name}"
                    else:
                        name_text = f"{last_name}, {first_name}"

                    # ----- Truncate long names safely -----
                    c.setFont("Helvetica-Bold", 12)
                    while c.stringWidth(name_text, "Helvetica-Bold", 12) > MAX_NAME_WIDTH:
                        name_text = name_text[:-1]
                        if len(name_text) == 0:
                            break
                    if c.stringWidth(name_text, "Helvetica-Bold", 12) > MAX_NAME_WIDTH:
                        name_text = name_text[:-1] + "…"

                    name_width = c.stringWidth(name_text, "Helvetica-Bold", 12)

                    # ----- Table label -----
                    if table_raw:
                        if table_prefix and table_raw.isdigit():
                            table_text = f"{table_prefix} {table_raw}"
                        else:
                            table_text = table_raw
                    else:
                        table_text = ""

                    table_width = c.stringWidth(table_text, "Helvetica", 12)

                    # ----- Draw name -----
                    c.setFont("Helvetica-Bold", 12)
                    c.drawString(LEFT_X, y, name_text)

                    # ----- Dot leaders -----
                    if table_text:
                        available = TABLE_X - (LEFT_X + name_width)
                        dot_width = c.stringWidth(".", "Helvetica", 12)
                        dots = "." * max(0, int(available / dot_width))

                        c.setFont("Helvetica", 12)
                        c.drawString(LEFT_X + name_width, y, dots)

                        # ----- Draw table -----
                        c.drawString(TABLE_X, y, table_text)

                    y -= 20  # spacing between guests

                # ----- Footer -----
                c.setFont("Helvetica-Oblique", 8)
                c.drawString(50, 20, "Made with TableFinder")
                c.drawRightString(width - 20, 20, str(page_number))
                c.showPage()
                page_number += 1

            c.save()
            pdf_bytes = pdf_buffer.getvalue()

            # --- Streamlit download button ---
            st.download_button(
                label="Download Guest List PDF",
                data=pdf_bytes,
                file_name="guest_list.pdf",
                mime="application/pdf"
            )
        else:
            st.info("Add guests to generate the PDF")
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
df = load_csv_from_r2(BUCKET, csv_key)
guests = df.to_dict(orient="records")
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