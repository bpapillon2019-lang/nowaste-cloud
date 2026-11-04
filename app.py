import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import unicodedata
import requests
import re
import datetime

# Configuration de la page
st.set_page_config(
    page_title="NoWaste Cloud - Gestion d'Inventaire, Courses & Périmés",
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

def format_date_fr(date_str):
    """Convertit une date YYYY-MM-DD en JJ/MM/AAAA"""
    if not date_str:
        return ""
    try:
        dt = datetime.datetime.strptime(str(date_str).strip(), "%Y-%m-%d")
        return dt.strftime("%d/%m/%Y")
    except:
        return str(date_str)

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
            sheet_inv.append_row(["id", "name", "location", "expiry_date", "quantity", "unit", "category"])
        
        if "shopping_list" not in sheet_names:
            sheet_shop = spreadsheet.add_worksheet(title="shopping_list", rows=100, cols=5)
            sheet_shop.append_row(["id", "name", "quantity", "unit"])
            
        if "catalog" not in sheet_names:
            sheet_cat = spreadsheet.add_worksheet(title="catalog", rows=100, cols=3)
            sheet_cat.append_row(["product_name", "location_name", "category"])
            default_products = [
                "Beurre", "Crème fraîche", "Fromage", "Jambon", 
                "Lait", "Œufs", "Pâtes", "Poulet", "Riz", 
                "Steak haché", "Yaourt nature", "Merguez", "Cheddar"
            ]
            default_locations = [
                "Frigo ❄️", "Congélateur 🧊 - Tiroir 1", 
                "Congélateur 🧊 - Tiroir 2", "Congélateur 🧊 - Tiroir 3", 
                "Placard 📦"
            ]
            for p, l in zip(default_products + [""]*(len(default_locations)-len(default_products)), 
                            default_locations + [""]*(len(default_products)-len(default_products))):
                sheet_cat.append_row([p, l, ""])
                
        return spreadsheet
    except Exception as e:
        st.error(f"Erreur de connexion à Google Sheets : {e}")
        return None

db = init_google_sheets()

@st.cache_data(ttl=30)
def get_catalog_categories():
    """Récupère les catégories du catalogue de manière mise en cache pour éviter le quota 429"""
    if db is None:
        return {}
    try:
        cat_sheet = db.worksheet("catalog")
        records = cat_sheet.get_all_records()
        cat_map = {}
        for r in records:
            p_name = str(r.get("product_name", "")).strip().lower()
            c_name = str(r.get("category", "")).strip()
            if p_name and c_name:
                cat_map[p_name] = c_name
        return cat_map
    except:
        return {}

def categorize_product(name):
    catalog_cats = get_catalog_categories()
    clean_name = str(name).strip().lower()
    if clean_name in catalog_cats:
        return catalog_cats[clean_name]

    n = normalize_text(name)
    meat = ["poulet", "steak", "viande", "poisson", "jambon", "lardons", "saucisse", "boeuf", "veau", "porc", "dinde", "merguez"]
    dairy = ["lait", "beurre", "creme", "fromage", "yaourt", "lben", "faisselle", "cheddar", "gouda", "mozzarella", "emmental"]
    prepared = ["quiche", "pizza", "lasagne", "plat", "soupe", "tarte", "friand", "nuggets", "cordon bleu", "brandade"]
    eggs = ["oeuf", "œufs"]
    fruits_vegs = ["tomate", "salade", "carotte", "courgette", "pomme", "banana", "fruit", "legume", "champignon", "oignon"]
    
    if any(k in n for k in meat):
        return "🥩 Viandes & Poissons"
    elif any(k in n for k in dairy):
        return "🥛 Produits Laitiers"
    elif any(k in n for k in prepared):
        return "🍲 Produits préparés"
    elif any(k in n for k in eggs):
        return "🥚 Œufs"
    elif any(k in n for k in fruits_vegs):
        return "🍎 Fruits & Légumes"
    else:
        return "📦 Autres"

def save_product_category_to_catalog(product_name, category):
    """Sauvegarde ou met à jour la catégorie dans le catalogue"""
    if db is None:
        return
    try:
        cat_sheet = db.worksheet("catalog")
        records = cat_sheet.get_all_records()
        
        found_row = None
        for i, r in enumerate(records, start=2):
            if str(r.get("product_name", "")).strip().lower() == product_name.strip().lower():
                found_row = i
                break
        
        if found_row:
            cat_sheet.update_cell(found_row, 3, category)
        else:
            cat_sheet.append_row([product_name, "", category])
        
        # Nettoie le cache pour prendre en compte le changement immédiatement
        st.cache_data.clear()
    except Exception as e:
        st.error(f"Erreur lors de la mise à jour du catalogue : {e}")

def get_all_inventory():
    if db is None:
        return []
    try:
        sheet = db.worksheet("inventory")
        records = sheet.get_all_records()
        items = []
        for r in records:
            try:
                p_name = str(r.get("name", ""))
                cat = str(r.get("category", ""))
                if not cat:
                    cat = categorize_product(p_name)
                
                items.append((
                    int(r.get("id", 1)),
                    p_name,
                    str(r.get("location", "")),
                    str(r.get("expiry_date", "")),
                    float(r.get("quantity", 1)),
                    str(r.get("unit", "unité(s)")),
                    cat
                ))
            except:
                pass
        return items
    except Exception:
        return st.session_state.get("cached_inventory", [])

def add_inventory_item(name, location, expiry_date, quantity, unit, category):
    if db is None:
        return
    try:
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
                sheet.update_cell(cell.row, 7, category)
        else:
            new_id = max([r.get("id", 0) for r in records], default=0) + 1
            sheet.append_row([new_id, name, location, expiry_date, quantity, unit, category])
        
        save_product_category_to_catalog(name, category)
    except Exception as e:
        st.error(f"Erreur lors de l'ajout à l'inventaire : {e}")

def update_item_category(item_id, product_name, new_category):
    if db is None:
        return
    try:
        sheet = db.worksheet("inventory")
        cell = sheet.find(str(item_id))
        if cell:
            sheet.update_cell(cell.row, 7, new_category)
        save_product_category_to_catalog(product_name, new_category)
    except Exception as e:
        st.error(f"Erreur de mise à jour de la catégorie : {e}")

def update_item_quantity_and_unit(item_id, new_qty, new_unit):
    if db is None:
        return
    try:
        sheet = db.worksheet("inventory")
        cell = sheet.find(str(item_id))
        if cell:
            sheet.update_cell(cell.row, 5, new_qty)
            sheet.update_cell(cell.row, 6, new_unit)
    except Exception as e:
        st.error(f"Erreur de mise à jour de la quantité/unité : {e}")

def update_item_location(item_id, new_loc, new_expiry):
    if db is None:
        return
    try:
        sheet = db.worksheet("inventory")
        cell = sheet.find(str(item_id))
        if cell:
            sheet.update_cell(cell.row, 3, new_loc)
            sheet.update_cell(cell.row, 4, new_expiry)
    except Exception as e:
        st.error(f"Erreur de mise à jour du lieu : {e}")

def delete_inventory_item(item_id):
    if db is None:
        return
    try:
        sheet = db.worksheet("inventory")
        cell = sheet.find(str(item_id))
        if cell:
            sheet.delete_rows(cell.row)
    except Exception as e:
        st.error(f"Erreur lors de la suppression : {e}")

def get_shopping_list():
    if db is None:
        return []
    try:
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
    except Exception:
        return []

def add_to_shopping_list(name, quantity, unit):
    if db is None:
        return
    try:
        sheet = db.worksheet("shopping_list")
        records = sheet.get_all_records()
        new_id = max([r.get("id", 0) for r in records], default=0) + 1
        sheet.append_row([new_id, name, quantity, unit])
    except Exception as e:
        st.error(f"Erreur lors de l'ajout aux courses : {e}")

def delete_shopping_item(item_id):
    if db is None:
        return
    try:
        sheet = db.worksheet("shopping_list")
        cell = sheet.find(str(item_id))
        if cell:
            sheet.delete_rows(cell.row)
    except Exception as e:
        st.error(f"Erreur lors de la suppression des courses : {e}")

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
    try:
        cat_sheet = db.worksheet("catalog")
        cat_sheet.append_row(["", new_loc, ""])
    except Exception as e:
        st.error(f"Erreur d'ajout de lieu : {e}")

def rename_location_in_db(old_loc, new_loc):
    if db is None:
        return
    try:
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
            cat_sheet.append_row(["", new_loc, ""])
    except Exception as e:
        st.error(f"Erreur de renommage de lieu : {e}")

def calculate_predicted_date(name, location):
    n_lower = normalize_text(name)
    l_lower = normalize_text(location)
    days = 7
    
    if "congel" in l_lower:
        days = 180
    elif "placard" in l_lower:
        days = 365
    else:
        meat = ["poulet", "steak", "viand", "poisson", "jambon", "merguez", "lardons"]
        dairy = ["beurre", "creme", "fromag", "yaourt", "lait", "cheddar", "gouda"]
        prepared = ["quiche", "pizza", "lasagne", "plat", "soupe", "tarte", "friand"]
        if any(k in n_lower for k in meat):
            days = 3
        elif any(k in n_lower for k in dairy):
            days = 14
        elif any(k in n_lower for k in prepared):
            days = 4
        elif "oeuf" in n_lower:
            days = 21
            
    return datetime.datetime.now().date() + datetime.timedelta(days=days)

# --- INTERFACE STREAMLIT ---
st.title("🍏 NoWaste Cloud - Gestion d'Inventaire, Courses & Périmés")

prod_catalog, loc_list = get_catalog_lists()

all_inv_items = get_all_inventory()
today_date = datetime.datetime.now().date()
alert_count = 0
for it in all_inv_items:
    try:
        exp_dt = datetime.datetime.strptime(str(it[3]).strip(), "%Y-%m-%d").date()
        if (exp_dt - today_date).days <= 7:
            alert_count += 1
    except:
        pass

expiry_tab_label = f"⏳ Périmés sous 7 jours ({alert_count})" if alert_count > 0 else "⏳ Périmés sous 7 jours"

# --- ONGLETS PRINCIPAUX ---
tab_shop, tab_inv, tab_expiry = st.tabs(["🛒 Liste de Courses", "📦 Mon Inventaire", expiry_tab_label])

# --- ONGLET 1 : LISTE DE COURSES ---
with tab_shop:
    st.subheader("Gestion de la Liste de Courses")
    
    col_s1, col_s2, col_s3, col_s4 = st.columns([3, 1, 2, 1])
    with col_s1:
        shop_prod_sel = st.selectbox("Produit", options=["-- Sélectionner ou taper --"] + prod_catalog, key="shop_prod_sel_box")
        shop_custom_name = st.text_input("Ou saisir le nom", key="shop_custom_input_box")
        final_shop_name = shop_custom_name.strip() if shop_custom_name.strip() else (shop_prod_sel if shop_prod_sel != "-- Sélectionner ou taper --" else "")
    with col_s2:
        shop_qty = st.number_input("Qté", min_value=0.1, value=1.0, step=1.0, key="shop_q_input_box")
    with col_s3:
        shop_unit_options = ["unité(s)", "g", "kg", "ml", "L", "boîte(s)", "pack(s)"]
        shop_unit = st.selectbox("Unité", options=shop_unit_options, key="shop_u_select_box")
    with col_s4:
        st.write("")
        st.write("")
        if st.button("➕ Ajouter aux courses", type="primary"):
            if final_shop_name:
                add_to_shopping_list(final_shop_name, shop_qty, shop_unit)
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
            if st.button("✔️ Valider les achats & Préparer le rangement", type="primary", use_container_width=True):
                if checked_to_validate:
                    st.session_state["validating_shop_items"] = checked_to_validate
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

        if st.session_state.get("validating_shop_items"):
            st.divider()
            st.markdown("### 🗄️ Configuration du rangement et des dates de péremption")
            st.info("Sélectionnez l'emplacement et ajustez la date de péremption pour chaque article avant de les valider dans l'inventaire.")

            default_target_loc = loc_list[0] if loc_list else "Frigo ❄️"
            batch_expiry_data = {}

            with st.form("batch_validation_form"):
                for s_item in st.session_state["validating_shop_items"]:
                    s_id, s_name, s_qty, s_unit = s_item
                    st.markdown(f"**{s_name}** ({s_qty} {s_unit})")
                    
                    c_loc, c_date = st.columns(2)
                    with c_loc:
                        chosen_loc = st.selectbox(f"Emplacement pour {s_name}", options=loc_list, index=loc_list.index(default_target_loc) if default_target_loc in loc_list else 0, key=f"val_loc_{s_id}")
                    with c_date:
                        pred_date = calculate_predicted_date(s_name, chosen_loc)
                        chosen_date = st.date_input(f"Date de péremption pour {s_name}", value=pred_date, key=f"val_date_{s_id}")
                    
                    batch_expiry_data[s_id] = (s_item, chosen_loc, chosen_date)
                    st.write("---")

                submitted_batch = st.form_submit_button("🚀 Confirmer le transfert dans l'inventaire", type="primary")
                if submitted_batch:
                    for s_id, (s_item, loc, exp_date) in batch_expiry_data.items():
                        _, s_name, s_qty, s_unit = s_item
                        auto_cat = categorize_product(s_name)
                        add_inventory_item(s_name, loc, exp_date.strftime("%Y-%m-%d"), s_qty, s_unit, auto_cat)
                        delete_shopping_item(s_id)
                    
                    st.session_state["validating_shop_items"] = []
                    st.success("🎉 Articles transférés dans l'inventaire avec succès !")
                    st.rerun()

# --- ONGLET 2 : INVENTAIRE ---
with tab_inv:
    st.subheader("Mon Inventaire")

    items = all_inv_items
    if items:
        st.session_state["cached_inventory"] = items

    search_query = st.session_state.get("sidebar_search", "")
    filter_loc = st.session_state.get("sidebar_loc_filter", "Tous les lieux")

    filtered_items = []
    for item in items:
        item_id, name, location, expiry_date, quantity, unit, category = item
        if search_query and normalize_text(search_query) not in normalize_text(name):
            continue
        if filter_loc != "Tous les lieux" and location != filter_loc:
            continue
        filtered_items.append(item)

    filtered_items.sort(key=lambda x: x[3])

    if not filtered_items:
        st.info("Aucun produit ne correspond aux critères dans l'inventaire.")

    unit_options = ["unité(s)", "g", "kg", "ml", "L", "boîte(s)", "pack(s)"]
    category_options = ["🥩 Viandes & Poissons", "🥛 Produits Laitiers", "🍲 Produits préparés", "🥚 Œufs", "🍎 Fruits & Légumes", "📦 Autres"]

    for item in filtered_items:
        item_id, name, location, expiry_date, quantity, unit, category = item

        expiry_fr = format_date_fr(expiry_date)
        status_text = "En cours"
        try:
            exp_obj = datetime.datetime.strptime(expiry_date.strip(), "%Y-%m-%d").date()
            delta = (exp_obj - today_date).days
            if delta < 0:
                status_text = f"Périmé ({abs(delta)} j)"
            elif 0 <= delta <= 3:
                status_text = f"Bientôt ({delta} j)"
        except:
            pass

        with st.container(border=True):
            col1, col2, col3, col4, col5, col6 = st.columns([2, 2, 1.8, 1, 1, 0.8])
            
            with col1:
                st.markdown(f"**{name}**")
                st.caption(f"Expire le : {expiry_fr}  •  [{status_text}]")
                
            with col2:
                cat_idx = category_options.index(category) if category in category_options else 5
                new_cat_choice = st.selectbox("Catégorie", options=category_options, index=cat_idx, key=f"cat_sel_{item_id}", label_visibility="collapsed")
                if new_cat_choice != category:
                    update_item_category(item_id, name, new_cat_choice)
                    st.rerun()

            with col3:
                new_location_choice = st.selectbox("Lieu", options=loc_list, index=loc_list.index(location) if location in loc_list else 0, key=f"loc_sel_{item_id}", label_visibility="collapsed")
                if new_location_choice != location:
                    new_exp = calculate_predicted_date(name, new_location_choice).strftime("%Y-%m-%d")
                    update_item_location(item_id, new_location_choice, new_exp)
                    st.rerun()
                
            with col4:
                new_qty = st.number_input("Qté", min_value=0.0, value=float(quantity), step=1.0, key=f"qty_input_{item_id}", label_visibility="collapsed")
            with col5:
                current_unit_idx = unit_options.index(unit) if unit in unit_options else 0
                new_unit = st.selectbox("Unité", options=unit_options, index=current_unit_idx, key=f"unit_sel_{item_id}", label_visibility="collapsed")

            if new_qty != quantity or new_unit != unit:
                if new_qty <= 0:
                    delete_inventory_item(item_id)
                else:
                    update_item_quantity_and_unit(item_id, new_qty, new_unit)
                st.rerun()

            with col6:
                if st.button("❌", key=f"del_{item_id}"):
                    delete_inventory_item(item_id)
                    st.rerun()

# --- ONGLET 3 : PÉRIMÉS SOUS 7 JOURS ---
with tab_expiry:
    st.subheader("⏳ Produits périmés ou à consommer dans les 7 jours")
    
    upcoming_expiry_items = []
    
    for item in all_inv_items:
        item_id, name, location, expiry_date, quantity, unit, category = item
        try:
            clean_date = str(expiry_date).strip()
            exp_obj = datetime.datetime.strptime(clean_date, "%Y-%m-%d").date()
            delta = (exp_obj - today_date).days
            if delta <= 7:
                upcoming_expiry_items.append((item, delta))
        except:
            pass

    if not upcoming_expiry_items:
        st.success("🎉 Aucun produit ne péremptera dans les 7 prochains jours !")
    else:
        categorized_dict = {}
        for item, delta in upcoming_expiry_items:
            cat = item[6] if len(item) > 6 and item[6] else categorize_product(item[1])
            if cat not in categorized_dict:
                categorized_dict[cat] = []
            categorized_dict[cat].append((item, delta))

        for cat in sorted(categorized_dict.keys()):
            st.markdown(f"### {cat}")
            for item, delta in categorized_dict[cat]:
                item_id, name, location, expiry_date, quantity, unit, category = item
                if quantity.is_integer():
                    quantity = int(quantity)
                
                expiry_fr = format_date_fr(expiry_date)
                if delta < 0:
                    badge = f"🔴 **Périmé depuis {abs(delta)} jour(s)**"
                elif delta == 0:
                    badge = f"⚠️ **Périme aujourd'hui !**"
                else:
                    badge = f"🟠 **Expire dans {delta} jour(s)** (le {expiry_fr})"
                
                with st.container(border=True):
                    c1, c2 = st.columns([3, 1])
                    with c1:
                        st.markdown(f"**{name}** — {quantity} {unit}")
                        st.caption(f"Emplacement : {location}")
                    with c2:
                        st.markdown(badge)

# --- BARRE LATÉRALE : FILTRES, FORMULAIRE & GESTION DES LIEUX ---
with st.sidebar:
    st.header("🔍 Filtrer l'inventaire")
    st.text_input("Filtrer par article", key="sidebar_search")
    st.selectbox("Filtrer par emplacement", options=["Tous les lieux"] + loc_list, key="sidebar_loc_filter")

    st.divider()
    st.header("➕ Ajouter à l'inventaire")
    
    selected_prod = st.selectbox("Produit du catalogue", options=["-- Sélectionner ou taper --"] + prod_catalog, key="inv_cat_sel_box")
    custom_name = st.text_input("Ou saisir le nom", key="inv_custom_input_box")
    final_name = custom_name.strip() if custom_name.strip() else (selected_prod if selected_prod != "-- Sélectionner ou taper --" else "")

    default_cat_suggestion = categorize_product(final_name) if final_name else "📦 Autres"
    category_options = ["🥩 Viandes & Poissons", "🥛 Produits Laitiers", "🍲 Produits préparés", "🥚 Œufs", "🍎 Fruits & Légumes", "📦 Autres"]
    cat_default_idx = category_options.index(default_cat_suggestion) if default_cat_suggestion in category_options else 5
    
    selected_category = st.selectbox("Catégorie", options=category_options, index=cat_default_idx, key="inv_cat_input_box")

    selected_loc = st.selectbox("Emplacement", options=loc_list, key="inv_loc_input_box")

    col_q1, col_q2 = st.columns([1, 2])
    with col_q1:
        qty_input = st.number_input("Qté", min_value=0.1, value=1.0, step=1.0, key="inv_q_input_box")
    with col_q2:
        unit_options = ["unité(s)", "g", "kg", "ml", "L", "boîte(s)", "pack(s)"]
        unit_input = st.selectbox("Unité", options=unit_options, key="inv_u_select_box")

    predicted_date = calculate_predicted_date(final_name, selected_loc)
    expiry_input = st.date_input("Date de péremption", value=predicted_date)
    st.caption(f"Format JJ/MM/AAAA : {expiry_input.strftime('%d/%m/%Y')}")

    if st.button("Ajouter à l'inventaire", type="primary", use_container_width=True):
        if final_name:
            add_inventory_item(final_name, selected_loc, expiry_input.strftime("%Y-%m-%d"), qty_input, unit_input, selected_category)
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