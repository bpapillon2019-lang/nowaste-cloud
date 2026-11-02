import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import unicodedata
import requests
import re
import cv2
import numpy as np
from datetime import datetime, timedelta

# Configuration de la page
st.set_page_config(
    page_title="NoWaste Cloud - Gestion d'Inventaire",
    page_icon="🍏",
    layout="wide"
)

def normalize_text(text):
    if not text:
        return ""
    text = text.lower().replace("œ", "oe").replace("æ", "ae")
    text = ''.join(
        c for c in unicodedata.normalize('NFD', text) 
        if unicodedata.category(c) != 'Mn'
    )
    return text

# --- CONNEXION GOOGLE SHEETS (MODE CLOUD & LOCAL) ---
@st.cache_resource
def init_google_sheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        if "gcp_service_account" in st.secrets:
            # Mode Cloud (via les secrets Streamlit)
            creds_dict = dict(st.secrets["gcp_service_account"])
            creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        else:
            # Mode Local (via ton fichier JSON sur ton PC)
            creds = Credentials.from_service_account_file("service_account.json", scopes=scope)
            
        client = gspread.authorize(creds)
        spreadsheet = client.open("NoWaste_DB")
        
        # Vérification et création des onglets si nécessaire
        sheet_names = [ws.title for ws in spreadsheet.worksheets()]
        
        if "inventory" not in sheet_names:
            sheet_inv = spreadsheet.add_worksheet(title="inventory", rows=100, cols=10)
            sheet_inv.append_row(["id", "name", "location", "expiry_date", "quantity", "unit"])
        else:
            sheet_inv = spreadsheet.worksheet("inventory")
            
        if "catalog" not in sheet_names:
            sheet_cat = spreadsheet.add_worksheet(title="catalog", rows=100, cols=2)
            sheet_cat.append_row(["product_name", "location_name"])
            default_products = [
                "Beurre", "Crème fraîche", "Fromage", "Jambon", 
                "Lait", "Œufs", "Pâtes", "Poulet", "Riz", 
                "Steak haché", "Yaourt nature"
            ]
            default_locations = [
                "Frigo ❄️", "Congélateur 🧊 - Tiroir 1", 
                "Congélateur 🧊 - Tiroir 2", "Congélateur 🧊 - Tiroir 3", 
                "Placard 📦"
            ]
            for p, l in zip(default_products + [""]*(len(default_locations)-len(default_products)), 
                            default_locations + [""]*(len(default_products)-len(default_products))):
                sheet_cat.append_row([p, l])
                
        return spreadsheet
    except Exception as e:
        st.error(f"Erreur de connexion à Google Sheets : {e}")
        return None

db = init_google_sheets()

def get_all_inventory():
    if db is None:
        return []
    sheet = db.worksheet("inventory")
    records = sheet.get_all_records()
    items = []
    for r in records:
        try:
            items.append((
                int(r.get("id", 1)),
                str(r.get("name", "")),
                str(r.get("location", "")),
                str(r.get("expiry_date", "")),
                float(r.get("quantity", 1)),
                str(r.get("unit", "unité(s)"))
            ))
        except:
            pass
    return items

def add_inventory_item(name, location, expiry_date, quantity, unit):
    if db is None:
        return
    sheet = db.worksheet("inventory")
    records = sheet.get_all_records()
    new_id = max([r.get("id", 0) for r in records], default=0) + 1
    sheet.append_row([new_id, name, location, expiry_date, quantity, unit])
    
    cat_sheet = db.worksheet("catalog")
    prods = [row.get("product_name") for row in cat_sheet.get_all_records() if row.get("product_name")]
    if name not in prods:
        cat_sheet.append_row([name, ""])

def update_item_quantity(item_id, new_qty):
    if db is None:
        return
    sheet = db.worksheet("inventory")
    cell = sheet.find(str(item_id))
    if cell:
        sheet.update_cell(cell.row, 5, new_qty)

def delete_inventory_item(item_id):
    if db is None:
        return
    sheet = db.worksheet("inventory")
    cell = sheet.find(str(item_id))
    if cell:
        sheet.delete_rows(cell.row)

def get_catalog_lists():
    if db is None:
        return ["Beurre", "Lait"], ["Frigo ❄️", "Placard 📦"]
    sheet = db.worksheet("catalog")
    records = sheet.get_all_records()
    products = list(set([r.get("product_name") for r in records if r.get("product_name")]))
    locations = list(set([r.get("location_name") for r in records if r.get("location_name")]))
    products.sort()
    locations.sort()
    if not locations:
        locations = ["Frigo ❄️", "Placard 📦"]
    return products, locations

def rename_location_in_db(old_loc, new_loc):
    if db is None:
        return
    inv_sheet = db.worksheet("inventory")
    cell_list = inv_sheet.findall(old_loc)
    for cell in cell_list:
        if cell.col == 3:
            inv_sheet.update_cell(cell.row, 3, new_loc)
            
    cat_sheet = db.worksheet("catalog")
    loc_cells = cat_sheet.findall(old_loc)
    for cell in loc_cells:
        if cell.col == 2:
            cat_sheet.update_cell(cell.row, 2, new_loc)
    if not loc_cells:
        cat_sheet.append_row(["", new_loc])

def calculate_predicted_date(name, location):
    n_lower = normalize_text(name)
    l_lower = normalize_text(location)
    days = 7
    
    if "congel" in l_lower:
        days = 180
    elif "placard" in l_lower:
        days = 365
    else:
        meat = ["poulet", "steak", "viand", "poisson", "jambon"]
        dairy = ["beurre", "creme", "fromag", "yaourt", "lait"]
        if any(k in n_lower for k in meat):
            days = 3
        elif any(k in n_lower for k in dairy):
            days = 14
        elif "oeuf" in n_lower:
            days = 21
            
    return datetime.now().date() + timedelta(days=days)

# Gestion de la session pour le scan
if "scanned_product_name" not in st.session_state:
    st.session_state["scanned_product_name"] = ""
if "scanned_qty" not in st.session_state:
    st.session_state["scanned_qty"] = 1.0

# --- INTERFACE STREAMLIT ---

st.title("🍏 NoWaste Cloud - Gestion d'Inventaire")

prod_catalog, loc_list = get_catalog_lists()

with st.sidebar:
    st.header("📷 Scanner de code-barres")
    picture = st.camera_input("Prendre en photo le code-barres")
    
    barcode_data = ""
    
    if picture is not None:
        bytes_data = picture.getvalue()
        np_arr = np.frombuffer(bytes_data, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        
        # --- AMÉLIORATION DE LA DÉTECTION ---
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        
        detector = cv2.barcode.BarcodeDetector()
        res = detector.detectAndDecode(gray)
        
        if len(res) == 4:
            retval, decoded_info, decoded_type, points = res
            if retval and len(decoded_info) > 0 and decoded_info[0]:
                barcode_data = decoded_info[0]
        else:
            retval, decoded_info = res[0], res[1]
            if retval and len(decoded_info) > 0 and decoded_info[0]:
                barcode_data = decoded_info[0]
                
        # Seconde passe sur l'image couleur originale si besoin
        if not barcode_data:
            res_orig = detector.detectAndDecode(frame)
            if len(res_orig) == 4 and res_orig[0] and len(res_orig[1]) > 0 and res_orig[1][0]:
                barcode_data = res_orig[1][0]
            elif len(res_orig) == 2 and res_orig[0] and len(res_orig[1]) > 0 and res_orig[1][0]:
                barcode_data = res_orig[1][0]

        if barcode_data:
            st.success(f"Code détecté : {barcode_data}")
            url = f"https://world.openfoodfacts.org/api/v0/product/{barcode_data}.json"
            headers = {'User-Agent': 'NoWasteCloud_Bertrand - Python App - Version 1.0'}
            try:
                response = requests.get(url, headers=headers, timeout=5)
                data = response.json()
                if data.get('status') == 1:
                    p_name = data['product'].get('product_name', 'Sans nom')
                    brand = data['product'].get('brands', '')
                    qty_str = data['product'].get('quantity', '')
                    
                    st.session_state["scanned_product_name"] = f"{p_name} {brand}".strip()
                    if qty_str:
                        match = re.match(r"([\d\.]+)\s*(.*)", qty_str)
                        if match:
                            st.session_state["scanned_qty"] = float(match.group(1))
                    st.rerun()
                else:
                    st.warning("Produit inconnu dans Open Food Facts.")
            except Exception as e:
                st.error(f"Erreur API : {e}")
        else:
            st.warning("⚠️ Code non détecté. 💡 Rapproche bien le code-barres (10-15 cm) en évitant les reflets directs.")

    st.divider()
    st.header("➕ Ajouter un produit")
    
    selected_prod = st.selectbox("Produit du catalogue", options=["-- Sélectionner ou taper --"] + prod_catalog)
    default_name = st.session_state["scanned_product_name"]
    
    custom_name = st.text_input("Nom personnalisé / scanné", value=default_name)
    
    final_name = custom_name.strip() if custom_name.strip() else (selected_prod if selected_prod != "-- Sélectionner ou taper --" else "")

    selected_loc = st.selectbox("Emplacement", options=loc_list)

    col_q1, col_q2 = st.columns([1, 2])
    with col_q1:
        qty_input = st.number_input("Qté", min_value=0.1, value=st.session_state["scanned_qty"], step=1.0)
    with col_q2:
        unit_input = st.selectbox("Unité", options=["unité(s)", "g", "kg", "ml", "L", "boîte(s)", "pack(s)"], index=0)

    predicted_date = calculate_predicted_date(final_name, selected_loc)
    expiry_input = st.date_input("Date de péremption", value=predicted_date)

    if st.button("Ajouter à l'inventaire", type="primary", use_container_width=True):
        if final_name:
            add_inventory_item(final_name, selected_loc, expiry_input.strftime("%Y-%m-%d"), qty_input, unit_input)
            st.session_state["scanned_product_name"] = ""
            st.session_state["scanned_qty"] = 1.0
            st.success(f"Ajouté : {final_name}")
            st.rerun()
        else:
            st.error("Veuillez indiquer un nom de produit.")

    st.divider()
    st.header("⚙️ Gestion des lieux")
    with st.expander("Renommer un emplacement"):
        old_loc_to_rename = st.selectbox("Lieu à modifier", options=loc_list, key="rename_sel")
        new_loc_name = st.text_input("Nouveau nom du lieu")
        if st.button("Appliquer le renommage"):
            if new_loc_name.strip() and old_loc_to_rename != new_loc_name.strip():
                rename_location_in_db(old_loc_to_rename, new_loc_name.strip())
                st.success("Emplacement mis à jour !")
                st.rerun()

    st.divider()
    st.header("🔍 Filtres")
    search_query = st.text_input("Rechercher par nom")
    filter_loc = st.selectbox("Filtrer par lieu", options=["Tous les lieux"] + loc_list)

# --- ZONE PRINCIPALE : LISTE DES PRODUITS ---

items = get_all_inventory()

filtered_items = []
for item in items:
    item_id, name, location, expiry_date, quantity, unit = item
    if search_query and normalize_text(search_query) not in normalize_text(name):
        continue
    if filter_loc != "Tous les lieux" and location != filter_loc:
        continue
    filtered_items.append(item)

filtered_items.sort(key=lambda x: x[3])

today = datetime.now().date()
expiring_soon = 0
expired_count = 0

for item in filtered_items:
    try:
        exp_obj = datetime.strptime(item[3], "%Y-%m-%d").date()
        delta = (exp_obj - today).days
        if delta < 0:
            expired_count += 1
        elif 0 <= delta <= 3:
            expiring_soon += 1
    except:
        pass

if expired_count > 0 or expiring_soon > 0:
    st.warning(f"⚠️ Alertes : {expired_count} produit(s) périmé(s) | {expiring_soon} produit(s) à consommer rapidement.")

st.subheader(f"Inventaire ({len(filtered_items)} produits)")

if not filtered_items:
    st.info("Aucun produit dans l'inventaire.")

for item in filtered_items:
    item_id, name, location, expiry_date, quantity, unit = item
    
    if quantity.is_integer():
        quantity = int(quantity)

    with st.container(border=True):
        col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
        
        with col1:
            st.markdown(f"**{name}**")
            st.caption(f"Qté : {quantity} {unit}  •  Expire le : {expiry_date}")
            
        with col2:
            st.markdown(f"📍 _{location}_")
            
        with col3:
            subcol1, subcol2, subcol3 = st.columns(3)
            with subcol1:
                if st.button("➖", key=f"minus_{item_id}"):
                    new_q = quantity - 1
                    if new_q <= 0:
                        delete_inventory_item(item_id)
                    else:
                        update_item_quantity(item_id, new_q)
                    st.rerun()
            with subcol2:
                st.write(f"**{quantity}**")
            with subcol3:
                if st.button("➕", key=f"plus_{item_id}"):
                    new_q = quantity + 1
                    update_item_quantity(item_id, new_q)
                    st.rerun()

        with col4:
            if st.button("❌", key=f"del_{item_id}"):
                delete_inventory_item(item_id)
                st.rerun()