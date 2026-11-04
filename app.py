import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import unicodedata
import requests
import re
import datetime
from streamlit_mic_recorder import speech_to_text

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
    
    # Optimisation : Gestion sécurisée et évitant le spam d'API sur le catalogue
    try:
        cat_sheet = db.worksheet("catalog")
        prods = [str(col) for col in cat_sheet.col_values(1) if col]
        if name not in prods:
            cat_sheet.append_row([name, ""])
    except Exception:
        pass

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
    
    try:
        cat_sheet = db.worksheet("catalog")
        prods = [str(col) for col in cat_sheet.col_values(1) if col]
        if name not in prods:
            cat_sheet.append_row([name, ""])
    except Exception:
        pass

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
    try:
        sheet = db.worksheet("catalog")
        records = sheet.get_all_records()
        products = list({str(r.get("product_name")) for r in records if r.get("product_name")})
        locations = list({str(r.get("location_name")) for r in records if r.get("location_name")})
        products.sort()
        locations.sort()
        if not locations:
            locations = ["Frigo ❄️", "Placard 📦"]
        return products, locations
    except Exception:
        return ["Beurre", "Lait"], ["Frigo ❄️", "Placard 📦"]

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

# --- ANALYSEUR VOCAL ---
def parse_voice_to_form(command_text):
    original_text = command_text.strip()
    text = normalize_text(original_text)
    
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

    unit = "unité(s)"
    unit_mapping = {"g": "g", "gramme": "g", "grammes": "g", "kg": "kg", "kilo": "kg", "kilos": "kg", "ml": "ml", "litre": "L", "litres": "L", "l": "L", "boite": "boîte(s)", "boites": "boîte(s)", "pack": "pack(s)", "packs": "pack(s)"}
    for w, u_val in unit_mapping.items():
        if f" {w} " in f" {text} ":
            unit = u_val
            break

    stop_words = [
        "ajoute", "ajouter", "mets", "mettre", "remets", "rajoute", "note", "prends",
        "retire", "retirer", "supprime", "supprimer", "enleve", "enlève",
        "dans", "l", "inventaire", "les", "courses", "de", "du", "la", "au", "stock", "liste", "acheter",
        "un", "une", "des", "le", "les", "et", "à", "a", "g", "grammes", "kg", "kilos", "ml", "l", "litres", "boite", "boites", "pack", "packs"
    ]
    
    words = text.split()
    filtered_words = [w for w in words if w not in stop_words and not w.isdigit()]
    
    product_name = " ".join(filtered_words).strip().capitalize()
    if not product_name:
        product_name = original_text.capitalize()

    target = "shopping" if any(w in text for w in ["courses", "liste", "acheter", "achat"]) else "inventory"
    return target, product_name, qty, unit

# --- ÉTATS DE SESSION ---
if "inv_product" not in st.session_state:
    st.session_state["inv_product"] = ""
if "inv_qty" not in st.session_state:
    st.session_state["inv_qty"] = 1.0
if "inv_unit" not in st.session_state:
    st.session_state["inv_unit"] = "unité(s)"

if "shop_product" not in st.session_state:
    st.session_state["shop_product"] = ""
if "shop_qty" not in st.session_state:
    st.session_state["shop_qty"] = 1.0
if "shop_unit" not in st.session_state:
    st.session_state["shop_unit"] = "unité(s)"

# --- INTERFACE STREAMLIT ---
st.title("🍏 NoWaste Cloud - Gestion d'Inventaire, Courses & Recettes")

prod_catalog, loc_list = get_catalog_lists()

# --- ONGLETS PRINCIPAUX ---
tab_shop, tab_inv, tab_recipes = st.tabs(["🛒 Liste de Courses", "📦 Mon Inventaire", "🍳 Idées de Recettes"])

# --- ONGLET 1 : LISTE DE COURSES ---
with tab_shop:
    st.subheader("Gestion de la Liste de Courses")
    
    st.markdown("**🎙️ Dictée vocale (Liste de Courses) :**")
    voice_shop_text = speech_to_text(language='fr-FR', start_prompt="🎤 Parler", stop_prompt="🛑 Arrêter", key='STT_shop')
    
    if voice_shop_text:
        target, p_name, p_qty, p_unit = parse_voice_to_form(voice_shop_text)
        st.session_state["shop_product"] = p_name
        st.session_state["shop_qty"] = p_qty
        st.session_state["shop_unit"] = p_unit
        st.success(f"🛒 Formulaire mis à jour : **{p_qty} {p_unit} de {p_name}**")
        st.rerun()

    col_s1, col_s2, col_s3, col_s4 = st.columns([3, 1, 2, 1])
    with col_s1:
        shop_prod_sel = st.selectbox("Produit", options=["-- Sélectionner ou taper --"] + prod_catalog, key="shop_prod_sel_box")
        shop_custom_name = st.text_input("Ou saisir le nom", value=st.session_state["shop_product"], key="shop_custom_input_box")
        final_shop_name = shop_custom_name.strip() if shop_custom_name.strip() else (shop_prod_sel if shop_prod_sel != "-- Sélectionner ou taper --" else "")
    with col_s2:
        shop_qty = st.number_input("Qté", min_value=0.1, value=float(st.session_state["shop_qty"]), step=1.0, key="shop_q_input_box")
    with col_s3:
        shop_unit_options = ["unité(s)", "g", "kg", "ml", "L", "boîte(s)", "pack(s)"]
        default_shop_unit_idx = shop_unit_options.index(st.session_state["shop_unit"]) if st.session_state["shop_unit"] in shop_unit_options else 0
        shop_unit = st.selectbox("Unité", options=shop_unit_options, index=default_shop_unit_idx, key="shop_u_select_box")
    with col_s4:
        st.write("")
        st.write("")
        if st.button("➕ Ajouter aux courses", type="primary"):
            if final_shop_name:
                add_to_shopping_list(final_shop_name, shop_qty, shop_unit)
                st.session_state["shop_product"] = ""
                st.session_state["shop_qty"] = 1.0
                st.session_state["shop_unit"] = "unité(s)"
                st.success(f"Ajouté aux courses : {final_shop_name}")
                st.rerun()

    st.divider()
    shopping_items = get_shopping_list()
    
    if not shopping_items:
        st.info("La liste de courses est vide.")
    else:
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
                    default_target_loc = loc_list[0] if loc_list else "Frigo ❄️"
                    for s_item in checked_to_validate:
                        s_id, s_name, s_qty, s_unit = s_item
                        pred_date = calculate_predicted_date(s_name, default_target_loc)
                        add_inventory_item(s_name, default_target_loc, pred_date.strftime("%Y-%m-%d"), s_qty, s_unit)
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

# --- BARRE LATÉRALE : FORMULAIRE D'INVENTAIRE & LIEUX ---
with st.sidebar:
    st.header("➕ Ajouter à l'inventaire")
    
    st.markdown("**🎙️ Dictée vocale pour l'inventaire :**")
    voice_inv_text = speech_to_text(language='fr-FR', start_prompt="🎤 Parler", stop_prompt="🛑 Arrêter", key='STT_inv')
    
    if voice_inv_text:
        target, p_name, p_qty, p_unit = parse_voice_to_form(voice_inv_text)
        st.session_state["inv_product"] = p_name
        st.session_state["inv_qty"] = p_qty
        st.session_state["inv_unit"] = p_unit
        st.success(f"📦 Formulaire mis à jour : **{p_qty} {p_unit} de {p_name}**")
        st.rerun()

    selected_prod = st.selectbox("Produit du catalogue", options=["-- Sélectionner ou taper --"] + prod_catalog, key="inv_cat_sel_box")
    custom_name = st.text_input("Nom du produit", value=st.session_state["inv_product"], key="inv_custom_input_box")
    final_name = custom_name.strip() if custom_name.strip() else (selected_prod if selected_prod != "-- Sélectionner ou taper --" else "")

    selected_loc = st.selectbox("Emplacement", options=loc_list)

    col_q1, col_q2 = st.columns([1, 2])
    with col_q1:
        qty_input = st.number_input("Qté", min_value=0.1, value=float(st.session_state["inv_qty"]), step=1.0, key="inv_q_input_box")
    with col_q2:
        unit_options = ["unité(s)", "g", "kg", "ml", "L", "boîte(s)", "pack(s)"]
        default_unit_idx = unit_options.index(st.session_state["inv_unit"]) if st.session_state["inv_unit"] in unit_options else 0
        unit_input = st.selectbox("Unité", options=unit_options, index=default_unit_idx, key="inv_u_select_box")

    predicted_date = calculate_predicted_date(final_name, selected_loc)
    expiry_input = st.date_input("Date de péremption", value=predicted_date)

    if st.button("Ajouter à l'inventaire", type="primary", use_container_width=True):
        if final_name:
            add_inventory_item(final_name, selected_loc, expiry_input.strftime("%Y-%m-%d"), qty_input, unit_input)
            st.session_state["inv_product"] = ""
            st.session_state["inv_qty"] = 1.0
            st.session_state["inv_unit"] = "unité(s)"
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