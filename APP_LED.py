import flet as ft
import requests
import math
import os
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# ==========================================
# CREACIÓN DE CARPETAS SEGURAS (Evita errores en servidores nuevos)
# ==========================================
DIRECTORIO_RAIZ = os.getcwd()
CARPETA_UPLOADS = os.path.join(DIRECTORIO_RAIZ, "uploads")
CARPETA_ASSETS = os.path.join(DIRECTORIO_RAIZ, "assets")
os.makedirs(CARPETA_UPLOADS, exist_ok=True)
os.makedirs(CARPETA_ASSETS, exist_ok=True)

# Importamos las librerías del PDF y gráficas
try:
    import numpy as np
    import matplotlib
    matplotlib.use('Agg') # Fundamental para que no choque en servidores
    import matplotlib.pyplot as plt
    from fpdf import FPDF
except ImportError:
    pass

def main(page: ft.Page):
    page.title = "LED MEXICO - Gestión de Accesos Cloud"
    page.window.width = 950 
    page.window.height = 1000
    page.theme_mode = ft.ThemeMode.DARK
    page.scroll = "adaptive"
    page.padding = 20

    # ⚠️ 1. REEMPLAZA CON TU ENLACE DE RENDER (EL DEL MOTOR, SIN / AL FINAL)
    URL_SERVIDOR = "https://motor-led-mexico.onrender.com" 
    
    # ⚠️ 2. REEMPLAZA CON EL NOMBRE EXACTO DE TU ARCHIVO JSON DE GOOGLE
    ARCHIVO_CREDENCIALES_GOOGLE = "credenciales.json" 
    
    # Datos de Google Sheets
    ID_HOJA = "1B-q98Dl3TNxRX1yNXU9piCyTS4x2NvWDeY9EK3LvDzc"
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

    datos_pdf_global = {}

    # ==========================================
    # SISTEMA DE SEGURIDAD (LOGIN CON GOOGLE SHEETS)
    # ==========================================
    def validar_en_google_sheets(usuario, password):
        try:
            creds = Credentials.from_service_account_file(ARCHIVO_CREDENCIALES_GOOGLE, scopes=SCOPES)
            client = gspread.authorize(creds)
            hoja = client.open_by_key(ID_HOJA).sheet1
            registros = hoja.get_all_records()
            hoy = datetime.now()

            usuario_login = usuario.strip().lower()
            password_login = password.strip()

            for fila in registros:
                db_usuario = str(fila.get('Usuario', '')).strip().lower()
                db_password = str(fila.get('Password', '')).strip()
                db_fecha = str(fila.get('Fecha_Expiracion', '2000-01-01')).strip()
                db_status = str(fila.get('Status', '')).strip().upper()

                if db_usuario == usuario_login:
                    if db_password == password_login:
                        if db_status == "INACTIVO":
                            return False, "🚫 Usuario desactivado por el administrador"
                        try:
                            fecha_exp = datetime.strptime(db_fecha, "%Y-%m-%d")
                            if hoy <= fecha_exp: return True, "OK"
                            else: return False, f"⚠️ Acceso expirado el {db_fecha}"
                        except ValueError: return False, f"❌ Error de fecha en Drive (Usa AAAA-MM-DD)."
            return False, "❌ Usuario o contraseña incorrectos"
        except Exception as ex: return False, f"Error de conexión: {ex}"

    txt_error_login = ft.Text("", color="red", weight="bold", text_align="center")
    prg_login = ft.ProgressBar(width=300, visible=False)

    def intentar_entrar(e=None):
        usr = in_usuario.value.strip()
        pwd = in_password.value.strip()
        if not usr or not pwd:
            txt_error_login.value = "⚠️ Ingresa usuario y contraseña"; page.update(); return

        txt_error_login.value = "⏳ Verificando en la nube..."; txt_error_login.color = "orange"
        prg_login.visible = True; btn_login.disabled = True; page.update()

        exito, mensaje = validar_en_google_sheets(usr, pwd)
        if exito: pantalla_login.visible = False; pantalla_principal.visible = True
        else: txt_error_login.value = mensaje; txt_error_login.color = "red"; prg_login.visible = False; btn_login.disabled = False
        page.update()

    in_usuario = ft.TextField(label="Usuario LED México", width=300, text_align="center", on_submit=intentar_entrar)
    in_password = ft.TextField(label="Contraseña", password=True, can_reveal_password=True, width=300, text_align="center", on_submit=intentar_entrar)
    btn_login = ft.ElevatedButton("AUTENTICAR ACCESO", on_click=intentar_entrar, width=300, height=50, bgcolor="orange", color="white")
    
    pantalla_login = ft.Container(
        content=ft.Column([
            ft.Image(src="/logo.png", width=250, height=120, fit=ft.ImageFit.CONTAIN), 
            ft.Text("SISTEMA DE INICIO DE SESION PARA SISTEMAS FOTOVOLTAAICOS LED MEXICO", size=22, weight="bold", color="white"), 
            ft.Container(height=10), in_usuario, in_password, prg_login, btn_login, txt_error_login
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        alignment=ft.alignment.center, expand=True, margin=ft.margin.only(top=100)
    )

    # ==========================================
    # 1. MOTOR OCR Y FILEPICKER
    # ==========================================
    txt_estado_ocr = ft.Text("Listo para escanear recibo...", color="grey", italic=True)
    prg_ocr = ft.ProgressBar(width=300, visible=False)

    def on_archivo_subido(e: ft.FilePickerUploadEvent):
        if e.progress < 1: return 
        ruta_archivo = os.path.join(CARPETA_UPLOADS, e.file_name)
        try:
            tipo_mime = 'application/pdf' if e.file_name.lower().endswith('.pdf') else 'image/jpeg'
            with open(ruta_archivo, 'rb') as f:
                archivos_para_enviar = {'file': (e.file_name, f, tipo_mime)}
                respuesta = requests.post(f"{URL_SERVIDOR}/api/ocr", files=archivos_para_enviar)
                
                try: datos = respuesta.json()
                except Exception: datos = {"error": f"El servidor respondió con código {respuesta.status_code}."}

            if datos.get("exito"):
                txt_estado_ocr.value = "✅ ¡Recibo procesado con éxito!"; txt_estado_ocr.color = "green"
                if datos.get("tarifa_detectada"): actualizar_interfaz(datos["tarifa_detectada"])
                costos_ia = datos.get("costos_detectados", {})
                for campo_ui in columna_costos.controls:
                    for nombre_costo, valor_costo in costos_ia.items():
                        if nombre_costo.lower() in campo_ui.label.lower() and float(valor_costo) > 0:
                            campo_ui.value = str(valor_costo); campo_ui.color = "#2ECC71"

                if datos.get("subtotal_detectado"):
                    campos_costos["SUB"].value = str(datos["subtotal_detectado"]); campos_costos["SUB"].color = "#2ECC71"
                
                consumos_detectados = datos.get("consumos_detectados", [])
                if consumos_detectados:
                    for campo in entradas_historial: campo.value = "0"; campo.color = "white"
                    for i, valor in enumerate(consumos_detectados):
                        if i < len(entradas_historial):
                            entradas_historial[i].value = str(round(valor)); entradas_historial[i].color = "#2ECC71"
                page.update(); calcular_propuesta()
            else: 
                error_msg = datos.get('detail', datos.get('error', str(datos)))
                txt_estado_ocr.value = f"❌ Error Real de la Nube: {error_msg}"; txt_estado_ocr.color = "red"
        except Exception as ex: 
            txt_estado_ocr.value = f"❌ Error de conexión al motor: {ex}"; txt_estado_ocr.color = "red"
        finally: 
            prg_ocr.visible = False; btn_ocr.disabled = False; page.update()

    def procesar_archivo_seleccionado(e: ft.FilePickerResultEvent):
        if getattr(e, "files", None) is None or not e.files: return
        archivo = e.files[0]
        txt_estado_ocr.value = f"⏳ Enviando a la nube Render..."; txt_estado_ocr.color = "orange"
        prg_ocr.visible = True; btn_ocr.disabled = True; page.update()
        upload_url = page.get_upload_url(archivo.name, 60)
        file_picker.upload([ft.FilePickerUploadFile(archivo.name, upload_url=upload_url)])

    file_picker = ft.FilePicker(on_result=procesar_archivo_seleccionado, on_upload=on_archivo_subido)
    page.overlay.append(file_picker)
    btn_ocr = ft.ElevatedButton("📷 ESCANEAR RECIBO", bgcolor="#145A32", color="white", height=50, on_click=lambda _: file_picker.pick_files(allow_multiple=False, allowed_extensions=["pdf", "png", "jpg", "jpeg"]))
    contenedor_ocr = ft.Container(content=ft.Column([btn_ocr, ft.Row([prg_ocr, txt_estado_ocr], alignment=ft.MainAxisAlignment.CENTER)], horizontal_alignment=ft.CrossAxisAlignment.CENTER), padding=10, border=ft.border.all(1, "#2ECC71"), border_radius=10, margin=ft.margin.only(bottom=15))

    # ==========================================
    # 2. TABLAS Y LÓGICA 
    # ==========================================
    in_potencia = ft.TextField(label="Watts del Panel", value="600", keyboard_type="number", width=160, height=45)
    entradas_historial = [ft.TextField(label=f"Bimestre {i+1}", value="0", height=45, text_size=13, visible=(i < 6)) for i in range(12)]
    
    img_g1 = ft.Image(src="", width=420, height=250, fit=ft.ImageFit.CONTAIN, visible=False)
    img_g2 = ft.Image(src="", width=420, height=250, fit=ft.ImageFit.CONTAIN, visible=False)
    fila_graficas_web = ft.Row([img_g1, img_g2], alignment=ft.MainAxisAlignment.CENTER, scroll="auto")

    def alternar_periodos(e=None):
        es_mensual = switch_mensual.value
        for i, campo in enumerate(entradas_historial):
            campo.label = f"Mes {i+1}" if es_mensual else f"Bimestre {i+1}"
            campo.visible = True if es_mensual else (i < 6)
            if not es_mensual and i >= 6: campo.value = "0" 
        page.update()
        
    switch_mensual = ft.Switch(label="¿Recibo Mensual?", value=False, on_change=alternar_periodos)
    contenedor_historial = ft.Container(content=ft.Column([ft.Text("3. Historial (kWh)", weight="bold", color="#3498DB"), ft.Column(entradas_historial, spacing=5, scroll="auto", height=380)]), border=ft.border.all(1, "#3498DB"), padding=15, border_radius=10, expand=True)

    def crear_c(n, v): return ft.TextField(label=n, value=v, keyboard_type="number", height=45, text_size=13)
    campos_costos = {
        "01": [crear_c("Básico", "0"), crear_c("Intermedio 1", "0"), crear_c("Intermedio 2", "0"), crear_c("Excedente", "0")],
        "DAC": [crear_c("Cargo Fijo", "0"), crear_c("Energía Consumida", "0")],
        "PDBT": [crear_c("Suministro", "80"), crear_c("Distribución", "0"), crear_c("Capacidad", "0"), crear_c("Energía Total", "0")],
        "GDMTO": [crear_c("Suministro", "80"), crear_c("Distribución", "0"), crear_c("Capacidad", "0"), crear_c("Transmisión", "0"),  crear_c("CENACE", "0"), crear_c("SCnMEM", "0"), crear_c("Energía Neta", "0")],
        "GDMTH": [crear_c("Suministro", "150"), crear_c("Distribución", "0"), crear_c("Capacidad", "0"), crear_c("Transmisión", "0"), crear_c("CENACE", "0"), crear_c("SCnMEM", "0"), crear_c("Base", "0"), crear_c("Intermedia", "0"), crear_c("Punta", "0")],
        "SUB": crear_c("Subtotal Real ($)", "0")
    }
    columna_costos = ft.Column(spacing=5, scroll="auto", height=380)
    contenedor_costos = ft.Container(content=ft.Column([ft.Text("4. Costos del Recibo ($)", weight="bold", color="#3498DB"), columna_costos]), border=ft.border.all(1, "#3498DB"), padding=15, border_radius=10, expand=True)
    fila_tablas = ft.Row(controls=[contenedor_historial, contenedor_costos], vertical_alignment=ft.CrossAxisAlignment.START, spacing=15)

    tarifa_activa = ft.Text("PDBT", color="orange", weight="bold", size=20)
    
    def actualizar_interfaz(t):
        tarifa_activa.value = t; columna_costos.controls.clear()
        for k in campos_costos:
            if isinstance(campos_costos[k], list):
                for c in campos_costos[k]: c.color = "white"
            else: campos_costos[k].color = "white"
        if t in ["01", "1A", "1B", "1C", "1D", "1E", "1F"]: columna_costos.controls.extend(campos_costos["01"]); switch_mensual.value = False
        elif t == "DAC": columna_costos.controls.extend(campos_costos["DAC"]); switch_mensual.value = False
        elif t == "PDBT": columna_costos.controls.extend(campos_costos["PDBT"]); switch_mensual.value = False
        elif t == "GDMTO": columna_costos.controls.extend(campos_costos["GDMTO"]); switch_mensual.value = True
        elif t == "GDMTH": columna_costos.controls.extend(campos_costos["GDMTH"]); switch_mensual.value = True
        columna_costos.controls.append(campos_costos["SUB"]); alternar_periodos()
        
        btn_pdf.visible = False; btn_abrir_pdf.visible = False
        img_g1.visible = False; img_g2.visible = False
        page.update()

    def btn_t(txt): return ft.ElevatedButton(txt, on_click=lambda _: actualizar_interfaz(txt), bgcolor="#2874A6", color="white")
    grid_tarifas = ft.Column([ft.Row([btn_t("01"), btn_t("1A"), btn_t("1B"), btn_t("1C"), btn_t("1D")], scroll="auto"), ft.Row([btn_t("1E"), btn_t("1F"), btn_t("DAC"), btn_t("PDBT"), btn_t("GDMTO"), btn_t("GDMTH")], scroll="auto")])
    res_final = ft.Container(content=ft.Text("Ingresa datos", color="white"), padding=15, bgcolor="#1B2631", border_radius=10)

    def num_seguro(valor):
        try: return float(str(valor).replace("$", "").replace(",", "").strip())
        except: return 0.0

    def calcular_propuesta(e=None):
        res_final.content.value = "Calculando inteligencia financiera..."
        btn_pdf.visible = False; btn_abrir_pdf.visible = False
        img_g1.visible = False; img_g2.visible = False
        page.update()
        
        try:
            consumos_visibles = [x for x in entradas_historial if x.visible]
            consumos = [num_seguro(x.value) for x in consumos_visibles if num_seguro(x.value) > 0]
            if not consumos: res_final.content.value = "⚠️ Error: Ingresa consumos."; res_final.bgcolor = "#7B241C"; page.update(); return
            
            promedio_kwh = sum(consumos) / len(consumos)
            hsp = 4.6; eficiencia = 1.0; dias = 30 if switch_mensual.value else 60
            w_panel = num_seguro(in_potencia.value)
            if w_panel <= 0: w_panel = 600.0; in_potencia.value = "600"; page.update()
            
            generacion_diaria_un_panel = (w_panel / 1000) * hsp * eficiencia
            cant_final = math.ceil((promedio_kwh / dias) / generacion_diaria_un_panel)
            dict_costos = {c.label: num_seguro(c.value) for c in columna_costos.controls}
            paquete = {"tarifa": tarifa_activa.value, "potencia_panel_w": w_panel, "cantidad_paneles": cant_final, "hsp": hsp, "eficiencia": eficiencia, "es_mensual": switch_mensual.value, "consumos": consumos, "costos": dict_costos}
            
            r = requests.post(f"{URL_SERVIDOR}/api/calcular", json=paquete)
            d = r.json()

            if d.get("exito"):
                ahorro_periodo = num_seguro(d.get('ahorro_periodo', 0)); nuevo_pago = num_seguro(d.get('nuevo_pago', 0)); gen_kwh = num_seguro(d.get('generacion_periodo_kwh', 0))
                subtotal_usuario = next((num_seguro(c.value) for c in columna_costos.controls if "Subtotal" in c.label), 0)
                gasto_actual_estimado = subtotal_usuario if subtotal_usuario > 0 else (ahorro_periodo + nuevo_pago)
                costo_por_kwh = gasto_actual_estimado / promedio_kwh if promedio_kwh > 0 else 0
                
                c_list, p_list, np_list, a_list, b_list = [], [], [], [], []
                for campo in consumos_visibles:
                    c_val = num_seguro(campo.value)
                    if c_val == 0: continue
                    costo_estimado = c_val * costo_por_kwh
                    nuevo_pago_estimado = max((c_val - gen_kwh) * costo_por_kwh, nuevo_pago)
                    
                    c_list.append(c_val)
                    p_list.append(costo_estimado)
                    np_list.append(nuevo_pago_estimado)
                    a_list.append(max(0, costo_estimado - nuevo_pago_estimado))
                    b_list.append(c_val - gen_kwh)

                potencia_inst = (cant_final * w_panel) / 1000
                inversor_sug = potencia_inst / 1.2
                gen_diaria_total = generacion_diaria_un_panel * cant_final
                gen_anual = gen_diaria_total * 365
                co2 = gen_anual * 0.000457
                ahorro_anual = sum(a_list) * (12/len(consumos) if switch_mensual.value else 6/len(consumos))

                datos_pdf_global.update({
                    "tarifa": tarifa_activa.value, "paneles": cant_final, "watts": w_panel, "promedio": round(promedio_kwh, 2), 
                    "ahorro_anual": ahorro_anual, "pago_promedio": sum(p_list)/len(p_list), "gen_kwh": gen_kwh, "es_mensual": switch_mensual.value,
                    "potencia_inst": potencia_inst, "inversor_sug": inversor_sug, "gen_diaria": gen_diaria_total,
                    "gen_anual": gen_anual, "co2": co2, "hsp": hsp,
                    "c_list": c_list, "p_list": p_list, "a_list": a_list, "np_list": np_list, "b_list": b_list
                })
                
                # --- AQUÍ GENERAMOS LAS GRÁFICAS PARA LA PÁGINA WEB ---
                try:
                    import matplotlib.pyplot as plt
                    import numpy as np
                    n_periodos = len(consumos)
                    x = np.arange(n_periodos)
                    etiquetas = [f"P{i+1}" for i in range(n_periodos)]

                    fig1, ax1 = plt.subplots(figsize=(6, 3.5))
                    ax1.bar(x - 0.175, consumos, 0.35, label='Consumo', color='#E74C3C')
                    ax1.bar(x + 0.175, [gen_kwh]*n_periodos, 0.35, label='Generación', color='#2ECC71')
                    ax1.set_title('Historial de Energía (kWh)', fontsize=12, fontweight='bold', color='white')
                    ax1.set_xticks(x); ax1.set_xticklabels(etiquetas, color='white')
                    ax1.tick_params(axis='y', colors='white')
                    ax1.legend(facecolor='#1B2631', edgecolor='white', labelcolor='white')
                    
                    fig1.patch.set_facecolor('none')
                    ax1.set_facecolor('none')
                    fig1.tight_layout()
                    ruta_g1 = os.path.join(CARPETA_ASSETS, "g1.png"); fig1.savefig(ruta_g1, format='png'); plt.close(fig1)

                    fig2, ax2 = plt.subplots(figsize=(6, 3.5))
                    ax2.bar(x - 0.25, p_list, 0.25, label='Pago Actual', color='#E74C3C')
                    ax2.bar(x, a_list, 0.25, label='Ahorro', color='#2ECC71')
                    ax2.bar(x + 0.25, np_list, 0.25, label='Nuevo Pago', color='#3498DB')
                    ax2.set_title('Historial Económico ($)', fontsize=12, fontweight='bold', color='white')
                    ax2.set_xticks(x); ax2.set_xticklabels(etiquetas, color='white')
                    ax2.tick_params(axis='y', colors='white')
                    ax2.legend(facecolor='#1B2631', edgecolor='white', labelcolor='white')
                    
                    fig2.patch.set_facecolor('none')
                    ax2.set_facecolor('none')
                    fig2.tight_layout()
                    ruta_g2 = os.path.join(CARPETA_ASSETS, "g2.png"); fig2.savefig(ruta_g2, format='png'); plt.close(fig2)

                    timestamp = int(datetime.now().timestamp())
                    img_g1.src = f"/g1.png?t={timestamp}"
                    img_g2.src = f"/g2.png?t={timestamp}"
                    img_g1.visible = True
                    img_g2.visible = True
                except Exception as ex_graf:
                    print("Advertencia: No se pudieron mostrar las gráficas en pantalla:", ex_graf)

                res_final.content.value = f"✅ CALCULO COMPLETADO:\nPaneles: {cant_final} | Potencia: {round(potencia_inst,2)}kWp | Ahorro Anual: ${round(ahorro_anual, 2):,}"
                res_final.bgcolor = "#145A32"; btn_pdf.visible = True
            else: res_final.content.value = f"Error del Servidor: {d.get('error')}"; res_final.bgcolor = "#7B241C"
        except Exception as ex: res_final.content.value = f"Error de cálculo: {ex}"; res_final.bgcolor = "#7B241C"
        page.update()

    # ==========================================
    # CREADOR PROFESIONAL DE PDF
    # ==========================================
    def generar_y_compartir_pdf(e):
        btn_pdf.disabled = True
        res_final.content.value = "⏳ Construyendo documento PDF..."; page.update()
        
        try: 
            from fpdf import FPDF
        except ImportError: 
            res_final.content.value = "⚠️ Instala librerías: pip install fpdf matplotlib numpy"
            res_final.bgcolor = "#7B241C"; btn_pdf.disabled = False; page.update(); return
            
        try:
            consumos = datos_pdf_global.get('c_list', [])
            gen_kwh = datos_pdf_global.get('gen_kwh', 0)
            pagos = datos_pdf_global.get('p_list', [])
            ahorros = datos_pdf_global.get('a_list', [])
            nuevos_pagos = datos_pdf_global.get('np_list', [])
            balances = datos_pdf_global.get('b_list', [])
            n_periodos = len(consumos)

            pdf = FPDF()
            pdf.add_page()
            
            # --- 1. AGREGAMOS EL LOGO AL PDF ---
            ruta_logo = os.path.join(CARPETA_ASSETS, "logo.png")
            try:
                if os.path.exists(ruta_logo):
                    pdf.image(ruta_logo, x=10, y=8, w=35, type='PNG')
            except Exception: pass

            # Movemos el texto a la derecha del Logo
            pdf.set_xy(50, 10)
            pdf.set_font("Arial", 'B', 18); pdf.set_text_color(243, 156, 18)
            pdf.cell(0, 6, "LED MEXICO", ln=True, align="L")
            pdf.set_xy(50, 16)
            pdf.set_font("Arial", 'I', 10); pdf.set_text_color(100, 100, 100)
            pdf.cell(0, 5, "DISENO Y FABRICACION", ln=True, align="L")
            
            # --- SOLUCIÓN AL OVERLAP: BAJAMOS EL INICIO DEL DOCUMENTO DE 35 A 55 ---
            pdf.set_xy(10, 55) 
            pdf.set_font("Arial", 'B', 14); pdf.set_text_color(0, 0, 0)
            pdf.cell(0, 8, "Propuesta de Sistema Fotovoltaico", ln=True, align="L")
            pdf.set_font("Arial", '', 10)
            pdf.cell(0, 6, f"Fecha de generacion: {datetime.now().strftime('%d/%m/%Y')}", ln=True, align="L")
            pdf.ln(5)

            pdf.set_font("Arial", 'B', 10)
            pdf.set_fill_color(240, 240, 240)
            pdf.cell(95, 7, " Datos del Sistema", border=1, fill=True)
            pdf.cell(95, 7, " Datos Economicos", border=1, ln=True, fill=True)
            
            pdf.set_font("Arial", '', 10)
            def fila_datos(c1, v1, c2, v2):
                pdf.cell(47.5, 7, f" {c1}", border=1); pdf.set_font("Arial", 'B', 10)
                pdf.cell(47.5, 7, f" {v1}", border=1); pdf.set_font("Arial", '', 10)
                pdf.cell(47.5, 7, f" {c2}", border=1); pdf.set_font("Arial", 'B', 10)
                pdf.cell(47.5, 7, f" {v2}", border=1, ln=True); pdf.set_font("Arial", '', 10)

            fila_datos("Tarifa CFE", datos_pdf_global.get('tarifa', ''), "Pago Promedio", f"${datos_pdf_global.get('pago_promedio',0):,.0f}")
            fila_datos("Paneles", str(datos_pdf_global.get('paneles', '')), "Ahorro Anual", f"${datos_pdf_global.get('ahorro_anual',0):,.0f}")
            fila_datos("Potencia Inst.", f"{datos_pdf_global.get('potencia_inst',0):.2f} kWp", "Inversor Sug.", f"{datos_pdf_global.get('inversor_sug',0):.2f} kW")
            fila_datos("Gen. Diaria Prom.", f"{datos_pdf_global.get('gen_diaria',0):.2f} kWh", "Gen. Mensual Prom.", f"{datos_pdf_global.get('gen_kwh',0):.0f} kWh")
            fila_datos("Gen. Anual Total", f"{datos_pdf_global.get('gen_anual',0):,.0f} kWh", "CO2 Evitado", f"{datos_pdf_global.get('co2',0):.2f} Ton/ano")
            fila_datos("Ubicacion", "Mexico", "HSP Aplicado", f"{datos_pdf_global.get('hsp',0)} hrs")
            pdf.ln(8)

            pdf.set_font("Arial", 'B', 12)
            pdf.cell(0, 8, "Comparativa Energetica Detallada", ln=True)
            pdf.set_font("Arial", 'B', 9)
            anchos = [18, 25, 25, 22, 30, 30, 30]
            cabeceras = ["Periodo", "Consumo", "Gen. Solar", "Balance", "Pago Actual", "Ahorro", "Nuevo Pago"]
            
            for i in range(7): pdf.cell(anchos[i], 7, cabeceras[i], border=1, align="C", fill=True)
            pdf.ln()

            pdf.set_font("Arial", '', 9)
            for i in range(n_periodos):
                pdf.cell(anchos[0], 7, f"{i+1}", border=1, align="C")
                pdf.cell(anchos[1], 7, f"{consumos[i]:,.0f} kWh", border=1, align="C")
                pdf.cell(anchos[2], 7, f"{gen_kwh:,.0f} kWh", border=1, align="C")
                pdf.cell(anchos[3], 7, f"{balances[i]:,.0f} kWh", border=1, align="C")
                pdf.cell(anchos[4], 7, f"${pagos[i]:,.0f}", border=1, align="R")
                pdf.cell(anchos[5], 7, f"${ahorros[i]:,.0f}", border=1, align="R")
                pdf.cell(anchos[6], 7, f"${nuevos_pagos[i]:,.0f}", border=1, align="R")
                pdf.ln()
            
            pdf.set_font("Arial", 'B', 9)
            pdf.set_fill_color(240, 240, 240)
            pdf.cell(anchos[0], 7, "TOTAL", border=1, align="C", fill=True)
            pdf.cell(anchos[1], 7, f"{sum(consumos):,.0f} kWh", border=1, align="C", fill=True)
            pdf.cell(anchos[2], 7, f"{gen_kwh*n_periodos:,.0f} kWh", border=1, align="C", fill=True)
            pdf.cell(anchos[3], 7, f"{sum(balances):,.0f} kWh", border=1, align="C", fill=True)
            pdf.cell(anchos[4], 7, f"${sum(pagos):,.0f}", border=1, align="R", fill=True)
            pdf.cell(anchos[5], 7, f"${sum(ahorros):,.0f}", border=1, align="R", fill=True)
            pdf.cell(anchos[6], 7, f"${sum(nuevos_pagos):,.0f}", border=1, align="R", fill=True)
            pdf.ln(10)

            pdf.set_font("Arial", 'B', 11)
            pdf.cell(0, 6, "Propuesta Tecnica del Sistema:", ln=True)
            pdf.set_font("Arial", '', 10)
            texto_p = (f"Considerando su consumo y para cubrir los gastos reflejados en el recibo de CFE, se determina la necesidad de instalar {datos_pdf_global.get('paneles', '')} paneles solares de {datos_pdf_global.get('watts', '')} Watts de potencia. Este sistema solar fotovoltaico tendra la capacidad de generar aproximadamente {datos_pdf_global.get('gen_kwh',0):,.0f} kWh por periodo. En consecuencia, se propone la instalacion de un inversor con una capacidad de al menos {datos_pdf_global.get('inversor_sug',0):.2f} kW para gestionar eficientemente la energia producida.\n\nEl precio de los costos es aproximado y puede diferir del recibo.")
            pdf.multi_cell(0, 5, texto_p)

            # Insertamos las gráficas
            pdf.add_page()
            pdf.set_font("Arial", 'B', 14)
            pdf.cell(0, 10, "Analisis Grafico", ln=True, align="C")
            pdf.ln(5)
            
            ruta_g1 = os.path.join(CARPETA_ASSETS, "g1.png")
            ruta_g2 = os.path.join(CARPETA_ASSETS, "g2.png")
            try:
                if os.path.exists(ruta_g1): pdf.image(ruta_g1, x=25, y=None, w=160, type='PNG')
            except Exception: pass
            
            pdf.ln(10)
            try:
                if os.path.exists(ruta_g2): pdf.image(ruta_g2, x=25, y=None, w=160, type='PNG')
            except Exception: pass

            # ==========================================
            # DESCARGA DEL PDF
            # ==========================================
            timestamp = int(datetime.now().timestamp())
            nombre_archivo = f"Propuesta_LED_MEXICO_{timestamp}.pdf"
            ruta_pdf = os.path.join(CARPETA_ASSETS, nombre_archivo)
            
            pdf.output(ruta_pdf)
            
            btn_pdf.visible = False
            btn_abrir_pdf.url = f"/{nombre_archivo}"
            btn_abrir_pdf.url_target = "_blank"
            btn_abrir_pdf.visible = True
            
            res_final.content.value = "✅ ¡PDF Generado! Haz clic en el botón verde de abajo para abrirlo."
            res_final.bgcolor = "#145A32"
        except Exception as ex: 
            res_final.content.value = f"⚠️ Error PDF: {ex}"
            res_final.bgcolor = "#7B241C"
        
        btn_pdf.disabled = False
        page.update()

    btn_calcular = ft.ElevatedButton("CALCULAR SISTEMA", on_click=calcular_propuesta, width=350, height=60, bgcolor="orange", color="white")
    btn_pdf = ft.ElevatedButton("📄 GENERAR PDF CON GRÁFICAS", bgcolor="#34495E", color="white", width=350, height=50, visible=False, on_click=generar_y_compartir_pdf)
    btn_abrir_pdf = ft.ElevatedButton("✅ ABRIR / DESCARGAR PDF", bgcolor="#2ECC71", color="white", width=350, height=60, visible=False)

    pantalla_principal = ft.Column([
        ft.Row([
            ft.Image(src="/logo.png", width=120, height=60, fit=ft.ImageFit.CONTAIN), 
            ft.Text("LED MEXICO - Sistemas de interconexión", size=26, weight="bold", color="orange")
        ], alignment=ft.MainAxisAlignment.CENTER, spacing=20),
        contenedor_ocr, 
        ft.Text("1. Seleccionar Tarifa CFE Manualmente (Opcional)", weight="bold"),
        grid_tarifas, ft.Row([ft.Text("Tarifa Activa:"), tarifa_activa]), ft.Divider(),
        ft.Row([in_potencia, switch_mensual]), 
        fila_tablas, 
        fila_graficas_web, 
        ft.Column([btn_calcular, btn_pdf, btn_abrir_pdf], horizontal_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.CENTER),
        res_final
    ], visible=False)

    actualizar_interfaz("01")
    page.add(pantalla_login, pantalla_principal)

os.environ["FLET_SECRET_KEY"] = "LED_MEXICO_SEGURIDAD_123"
puerto = int(os.environ.get("PORT", 8080))

ft.app(target=main, view=ft.AppView.WEB_BROWSER, upload_dir=CARPETA_UPLOADS, assets_dir=CARPETA_ASSETS, host="0.0.0.0", port=puerto)
