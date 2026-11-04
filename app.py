import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import unicodedata
import requests
import re
import datetime

# Configuration de la page
st.set_page_config(
    page_title="NoWaste Cloud - Gestion d'Inventaire, Courses & Recettes",
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

# --- CONNEXION GOOGLE SHEETS ---
@st.cache_resource
def init_google_sheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        if "gcp_service_account" in st.secrets:
            creds_dict = dict(st.secrets["gcp_service_account"])
            creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        else:
            creds = Credentials.from_service_account_file("service_account.json", scopes=scope)
            
        client = gspread.authorize(creds)
        spreadsheet = client.open("NoWaste_DB")
        
        sheet_names = [ws.title for ws in spreadsheet.worksheets()]
        
        if "inventory" not in sheet_names:
            sheet_inv = spreadsheet.add_worksheet(title="inventory", rows=100, cols=10)
            sheet_inv.append_row(["id", "name", "location", "expiry_date", "quantity", "unit"])
        
        if "shopping_list" not in sheet_names:
            sheet_shop = spreadsheet.add_worksheet(title="shopping_list", rows=100, cols=5)
            sheet_shop.append_row(["id", "name", "quantity", "unit"])
            
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
    
    existing_row = None
    for r in records:
        if str(r.get("name", "")).strip().lower() == name.strip().lower() and str(r.get("unit", "")) == unit:
            existing_row = r
            break

    if existing_row:
        cell = sheet.find(str(existing_row["id"]))
        if cell:
            current_qty = float(existing_row.get("quantity", 0))
            new_qty = current_qty + quantity
            sheet.update_cell(cell.row, 5, new_qty)
    else:
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

def update_item_location(item_id, new_loc, new_expiry):
    if db is None:
        return
    sheet = db.worksheet("inventory")
    cell = sheet.find(str(item_id))
    if cell:
        sheet.update_cell(cell.row, 3, new_loc)
        sheet.update_cell(cell.row, 4, new_expiry)

def delete_inventory_item(item_id):
    if db is None:
        return
    sheet = db.worksheet("inventory")
    cell = sheet.find(str(item_id))
    if cell:
        sheet.delete_rows(cell.row)

def get_shopping_list():
    if db is None:
        return []
    sheet = db.worksheet("shopping_list")
    records = sheet.get_all_records()
    items = []
    for r in records:
        try:
            items.append((
                int(r.get("id", 1)),
                str(r.get("name", "")),
                float(r.get("quantity", 1)),
                str(r.get("unit", "unité(s)"))
            ))
        except:
            pass
    return items

def add_to_shopping_list(name, quantity, unit):
    if db is None:
        return
    sheet = db.worksheet("shopping_list")
    records = sheet.get_all_records()
    new_id = max([r.get("id", 0) for r in records], default=0) + 1
    sheet.append_row([new_id, name, quantity, unit])
    
    cat_sheet = db.worksheet("catalog")
    prods = [row.get("product_name") for row in cat_sheet.get_all_records() if row.get("product_name")]
    if name not in prods:
        cat_sheet.append_row([name, ""])

def delete_shopping_item(item_id):
    if db is None:
        return
    sheet = db.worksheet("shopping_list")
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

def add_location_in_db(new_loc):
    if db is None:
        return
    cat_sheet = db.worksheet("catalog")
    cat_sheet.append_row(["", new_loc])

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
            
    return datetime.datetime.now().date() + datetime.timedelta(days=days)

# --- ANALYSEUR DE COMMANDE ---
def process_command(command_text):
    original_text = command_text.strip()
    text = normalize_text(original_text)
    
    action = None
    if any(w in text for w in ["ajoute", "ajouter", "mets", "mettre", "remets", "rajoute", "note", "prends"]):
        action = "add"
    elif any(w in text for w in ["retire", "retirer", "supprime", "supprimer", "enleve", "enlève"]):
        action = "remove"
        
    if not action:
        return f"❌ Action non comprise dans : « {original_text} ». Essayez 'Ajoute du lait'."

    target = "shop"
    if any(w in text for w in ["inventaire", "frigo", "congelateur", "placard", "stock"]):
        target = "inventory"
    elif any(w in text for w in ["courses", "liste"]):
        target = "shop"

    qty = 1.0
    qty_match = re.search(r'\b(\d+([.,]\d+)?)\b', text)
    if qty_match:
        qty = float(qty_match.group(1).replace(',', '.'))
    else:
        word_to_num = {"un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10}
        for word, val in word_to_num.items():
            if f" {word} " in f" {text} ":
                qty = float(val)
                break

    stop_words = [
        "ajoute", "ajouter", "mets", "mettre", "remets", "rajoute", "note", "prends",
        "retire", "retirer", "supprime", "supprimer", "enleve", "enlève",
        "dans", "l", "inventaire", "les", "courses", "de", "du", "la", "au", "stock",
        "un", "une", "des", "le", "les", "et", "à", "a"
    ]
    
    words = text.split()
    filtered_words = [w for w in words if w not in stop_words and not w.isdigit()]
    
    product_name = " ".join(filtered_words).strip().capitalize()
    if not product_name:
        product_name = original_text.capitalize()

    _, loc_list = get_catalog_lists()

    if action == "add":
        if target == "inventory":
            default_loc = loc_list[0] if loc_list else "Frigo ❄️"
            pred_date = calculate_predicted_date(product_name, default_loc)
            add_inventory_item(product_name, default_loc, pred_date.strftime("%Y-%m-%d"), qty, "unité(s)")
            return f"✅ Ajouté à l'inventaire ({default_loc}) : {qty} x {product_name}"
        else:
            add_to_shopping_list(product_name, qty, "unité(s)")
            return f"✅ Ajouté aux courses : {qty} x {product_name}"
            
    elif action == "remove":
        if target == "inventory":
            inv_items = get_all_inventory()
            found = False
            for i_id, i_name, i_loc, i_exp, i_qty, i_unit in inv_items:
                if normalize_text(product_name) in normalize_text(i_name) or normalize_text(i_name) in normalize_text(product_name):
                    new_q = i_qty - qty
                    if new_q <= 0:
                        delete_inventory_item(i_id)
                    else:
                        update_item_quantity(i_id, new_q)
                    found = True
                    break
            if found:
                return f"🗑️ Retiré de l'inventaire : {product_name}"
            else:
                return f"⚠️ Produit '{product_name}' introuvable dans l'inventaire."
        else:
            shop_items = get_shopping_list()
            found = False
            for s_id, s_name, s_qty, s_unit in shop_items:
                if normalize_text(product_name) in normalize_text(s_name) or normalize_text(s_name) in normalize_text(product_name):
                    delete_shopping_item(s_id)
                    found = True
                    break
            if found:
                return f"🗑️ Retiré des courses : {product_name}"
            else:
                return f"⚠️ Produit '{product_name}' introuvable dans la liste de courses."

    return "Commande non traitée."

# --- INTERFACE STREAMLIT ---
st.title("🍏 NoWaste Cloud - Gestion d'Inventaire, Courses & Recettes")

prod_catalog, loc_list = get_catalog_lists()

# --- COMMANDE VOCALE / TEXTUELLE DIRECTE ET ROBUSTE ---
with st.container():
    st.markdown("### 🎙️ Assistant Vocal & Textuel Intelligent")
    st.markdown("Utilise le micro de ton clavier virtuel (smartphone ou PC) ou tape directement ta phrase (ex: *'Ajoute 3 lait dans l'inventaire'*).")
    
    # Utilisation d'un formulaire de saisie natif Streamlit (garantit 100% l'exécution de l'action)
    with st.form("voice_text_form", clear_on_submit=True):
        spoken_input = st.text_input("Commande vocale ou textuelle", placeholder="Ex: Ajoute 2 beurre dans l'inventaire")
        submitted = st.form_submit_button("Exécuter la commande", type="primary")
        
        if submitted and spoken_input:
            msg = process_command(spoken_input)
            if "✅" in msg or "🗑️" in msg:
                st.success(msg)
                st.rerun()
            else:
                st.warning(msg)

st.divider()

# --- BARRE LATÉRALE : AJOUT MANUEL & GESTION DES LIEUX ---
with st.sidebar:
    st.header("➕ Ajouter un produit")
    
    selected_prod = st.selectbox("Produit du catalogue", options=["-- Sélectionner ou taper --"] + prod_catalog)
    custom_name = st.text_input("Nom personnalisé")
    final_name = custom_name.strip() if custom_name.strip() else (selected_prod if selected_prod != "-- Sélectionner ou taper --" else "")

    selected_loc = st.selectbox("Emplacement", options=loc_list)

    col_q1, col_q2 = st.columns([1, 2])
    with col_q1:
        qty_input = st.number_input("Qté", min_value=0.1, value=1.0, step=1.0)
    with col_q2:
        unit_input = st.selectbox("Unité", options=["unité(s)", "g", "kg", "ml", "L", "boîte(s)", "pack(s)"], index=0)

    predicted_date = calculate_predicted_date(final_name, selected_loc)
    expiry_input = st.date_input("Date de péremption", value=predicted_date)

    if st.button("Ajouter à l'inventaire", type="primary", use_container_width=True):
        if final_name:
            add_inventory_item(final_name, selected_loc, expiry_input.strftime("%Y-%m-%d"), qty_input, unit_input)
            st.success(f"Ajouté : {final_name}")
            st.rerun()
        else:
            st.error("Veuillez indiquer un nom de produit.")

    st.divider()
    st.header("⚙️ Gestion des lieux")
    with st.expander("Ajouter ou Renommer un emplacement"):
        new_loc_add = st.text_input("Nom du nouveau lieu")
        if st.button("Créer l'emplacement"):
            if new_loc_add.strip():
                add_location_in_db(new_loc_add.strip())
                st.success("Lieu ajouté avec succès !")
                st.rerun()
                
        st.divider()
        old_loc_to_rename = st.selectbox("Lieu à modifier", options=loc_list, key="rename_sel")
        new_loc_name = st.text_input("Nouveau nom du lieu")
        if st.button("Appliquer le renommage"):
            if new_loc_name.strip() and old_loc_to_rename != new_loc_name.strip():
                rename_location_in_db(old_loc_to_rename, new_loc_name.strip())
                st.success("Emplacement mis à jour !")
                st.rerun()

# --- ONGLETS PRINCIPAUX ---
tab_shop, tab_inv, tab_recipes = st.tabs(["🛒 Liste de Courses", "📦 Mon Inventaire", "🍳 Idées de Recettes"])

# --- ONGLET 1 : LISTE DE COURSES ---
with tab_shop:
    st.subheader("Gestion de la Liste de Courses")
    
    col_s1, col_s2, col_s3, col_s4 = st.columns([3, 1, 2, 1])
    with col_s1:
        shop_prod_sel = st.selectbox("Produit", options=["-- Sélectionner ou taper --"] + prod_catalog, key="shop_prod")
        shop_custom_name = st.text_input("Ou saisir le nom", key="shop_custom")
        final_shop_name = shop_custom_name.strip() if shop_custom_name.strip() else (shop_prod_sel if shop_prod_sel != "-- Sélectionner ou taper --" else "")
    with col_s2:
        shop_qty = st.number_input("Qté", min_value=0.1, value=1.0, step=1.0, key="shop_q")
    with col_s3:
        shop_unit = st.selectbox("Unité", options=["unité(s)", "g", "kg", "ml", "L", "boîte(s)", "pack(s)"], key="shop_u")
    with col_s4:
        st.write("")
        st.write("")
        if st.button("➕ Ajouter", type="primary"):
            if final_shop_name:
                add_to_shopping_list(final_shop_name, shop_qty, shop_unit)
                st.success(f"Ajouté aux courses : {final_shop_name}")
                st.rerun()

    st.divider()
    shopping_items = get_shopping_list()
    
    if not shopping_items:
        st.info("La liste de courses est vide.")
    else:
        selected_target_loc = st.selectbox("Ranger les achats validés dans :", options=loc_list, key="target_loc")
        
        checked_to_validate = []
        for s_item in shopping_items:
            s_id, s_name, s_qty, s_unit = s_item
            if s_qty.is_integer():
                s_qty = int(s_qty)
            is_checked = st.checkbox(f"{s_name} — {s_qty} {s_unit}", key=f"shop_chk_{s_id}")
            if is_checked:
                checked_to_validate.append(s_item)

        col_act1, col_act2 = st.columns(2)
        with col_act1:
            if st.button("✔️ Valider les achats & Basculer en Inventaire", type="primary", use_container_width=True):
                if checked_to_validate:
                    for s_item in checked_to_validate:
                        s_id, s_name, s_qty, s_unit = s_item
                        pred_date = calculate_predicted_date(s_name, selected_target_loc)
                        add_inventory_item(s_name, selected_target_loc, pred_date.strftime("%Y-%m-%d"), s_qty, s_unit)
                        delete_shopping_item(s_id)
                    st.success("Achats basculés dans l'inventaire avec succès !")
                    st.rerun()
                else:
                    st.warning("Aucun article sélectionné.")
                    
        with col_act2:
            if st.button("🗑️ Retirer de la liste (sans ajouter)", use_container_width=True):
                if checked_to_validate:
                    for s_item in checked_to_validate:
                        s_id, s_name, s_qty, s_unit = s_item
                        delete_shopping_item(s_id)
                    st.success("Articles retirés de la liste de courses.")
                    st.rerun()
                else:
                    st.warning("Aucun article sélectionné.")

# --- ONGLET 2 : INVENTAIRE ---
with tab_inv:
    st.subheader("Mon Inventaire")
    
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        search_query = st.text_input("Rechercher par nom", key="inv_search")
    with col_f2:
        filter_loc = st.selectbox("Filtrer par lieu", options=["Tous les lieux"] + loc_list, key="inv_loc_filter")

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

    today = datetime.datetime.now().date()
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

    if not filtered_items:
        st.info("Aucun produit dans l'inventaire.")

    for item in filtered_items:
        item_id, name, location, expiry_date, quantity, unit = item
        
        if quantity.is_integer():
            quantity = int(quantity)

        status_text = "En cours"
        try:
            exp_obj = datetime.strptime(expiry_date, "%Y-%m-%d").date()
            delta = (exp_obj - today).days
            if delta < 0:
                status_text = f"Périmé ({abs(delta)} j)"
            elif 0 <= delta <= 3:
                status_text = f"Bientôt ({delta} j)"
        except:
            pass

        with st.container(border=True):
            col1, col2, col3, col4 = st.columns([3, 2, 3, 1])
            
            with col1:
                st.markdown(f"**{name}**")
                st.caption(f"Qté : {quantity} {unit}  •  Expire le : {expiry_date}  •  [{status_text}]")
                
            with col2:
                new_location_choice = st.selectbox("Lieu", options=loc_list, index=loc_list.index(location) if location in loc_list else 0, key=f"loc_sel_{item_id}", label_visibility="collapsed")
                if new_location_choice != location:
                    new_exp = calculate_predicted_date(name, new_location_choice).strftime("%Y-%m-%d")
                    update_item_location(item_id, new_location_choice, new_exp)
                    st.rerun()
                
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

# --- ONGLET 3 : RECETTES WEB INTELLIGENTES ---
with tab_recipes:
    st.subheader("🍳 Inspirations & Recettes Anti-Gaspi")
    
    if st.button("🔄 Actualiser les idées"):
        st.rerun()

    items = get_all_inventory()
    if not items:
        st.info("Votre inventaire est vide. Ajoutez des produits pour découvrir des suggestions de recettes !")
    else:
        inventory_items = [row[1].lower() for row in items]
        
        web_recipes_database = [
            {
                "title": "quiche lorraine maison ou tarte salée",
                "core": ["œufs", "lait", "crème fraîche"],
                "extras": ["Pâte brisée", "Lardons fumés ou dés de jambon", "Gruyère râpé"],
                "desc": "Une grande classique inspirée du web. Utilisez vos œufs et votre crème, et prévoyez d'acheter une pâte brisée et des lardons pour compléter."
            },
            {
                "title": "gratin de pâtes ou de riz crémeux au four",
                "core": ["pâtes", "riz", "crème fraîche", "fromage"],
                "extras": ["1 oignon", "500g de steak haché ou morceaux de poulet", "Légumes de saison (courgettes ou brocolis)"],
                "desc": "Idéal pour écouler vos féculents et votre crème. Achetez un peu de viande hachée ou de poulet ainsi qu'un légume vert pour un plat complet."
            },
            {
                "title": "poulet rôti ou poêlé aux herbes et pâtes/riz",
                "core": ["poulet", "beurre", "pâtes", "riz"],
                "extras": ["1 belle volaille ou filets de poulet", "Ail, échalotes", "Salade verte ou haricots verts"],
                "desc": "Faites dorer votre poulet au beurre et servez-le avec vos réserves de pâtes ou de riz. Pensez à acheter des légumes frais pour l'accompagnement."
            },
            {
                "title": "omelette du chef aux fines herbes et fromage",
                "core": ["œufs", "beurre", "fromage"],
                "extras": ["Champignons de Paris frais", "Persil ou ciboulette", "Salade en sachet"],
                "desc": "Parfait pour un repas express du soir. Ajoutez des champignons frais et une salade croquante à votre liste de courses."
            },
            {
                "title": "steaks hachés poêlés et risotto/pâtes express",
                "core": ["steak haché", "beurre"],
                "extras": ["Steaks frais de chez le boucher", "Tomates fraîches ou purée de tomates", "Oignons"],
                "desc": "Faites saisir vos steaks et préparez une belle sauce maison. Complétez avec des tomates fraîches et des oignons."
            },
            {
                "title": "crêpes gourmandes salées ou sucrées",
                "core": ["œufs", "lait", "beurre"],
                "extras": ["Farine de blé", "Jambon blanc", "Fromage râpé ou chocolat à tartiner"],
                "desc": "Une recette incontournable pour régaler toute la famille en vidant le frigo de son lait et de ses œufs."
            }
        ]

        matched_recipes = []
        for recipe in web_recipes_database:
            match_score = sum(1 for core_item in recipe["core"] if any(core_item in inv for inv in inventory_items))
            if match_score > 0:
                matched_recipes.append((recipe, match_score))

        matched_recipes.sort(key=lambda x: x[1], reverse=True)

        if not matched_recipes:
            st.info("Aucune recette web ne correspond précisément à vos ingrédients actuels pour l'instant.")
        else:
            for recipe, score in matched_recipes:
                with st.container(border=True):
                    st.markdown(f"### 🍲 {recipe['title'].capitalize()}")
                    
                    present_core = [c for c in recipe["core"] if any(c in inv for inv in inventory_items)]
                    if present_core:
                        st.markdown(f"✔️ **Dans votre inventaire :** {', '.join(present_core)}")
                        
                    st.markdown(f"🛒 **À acheter en plus (viande, légumes, frais) :** {', '.join(recipe['extras'])}")
                    st.write(recipe["desc"])