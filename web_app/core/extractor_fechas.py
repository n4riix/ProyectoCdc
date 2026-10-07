import re
from datetime import datetime

# Mapeo de meses en español con tolerancia a errores típicos de OCR (ej. Encro -> Enero)
MESES_ES = {
    'enero': '01', 'ene': '01', 'encro': '01', 'enern': '01', 'ener0': '01',
    'febrero': '02', 'feb': '02', 'febrer0': '02', 'tebrero': '02',
    'marzo': '03', 'mar': '03', 'marz0': '03',
    'abril': '04', 'abr': '04',
    'mayo': '05', 'may': '05', 'may0': '05',
    'junio': '06', 'jun': '06', 'juni0': '06',
    'julio': '07', 'jul': '07', 'juli0': '07',
    'agosto': '08', 'ago': '08', 'agost0': '08',
    'septiembre': '09', 'sep': '09', 'sept': '09', 'setiembre': '09', 'septiembr0': '09',
    'octubre': '10', 'oct': '10', 'octubr0': '10',
    'noviembre': '11', 'nov': '11', 'noviembr0': '11',
    'diciembre': '12', 'dic': '12', 'diciembr0': '12'
}

# Palabras clave de anclaje para identificar la Fecha Principal de Expedición / Celebración
ANCLAJES_EXPEDICION = [
    r'se\s+celebr[oó]',
    r'celebrad[ao]',
    r'en\s+fecha',
    r'de\s+fecha',
    r'con\s+fecha',
    r'otorgad[ao]',
    r'otorgamiento',
    r'expedid[ao]',
    r'expide',
    r'fecha\s+de\s+emisi[oó]n',
    r'emitid[ao]',
    r'lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo',
    r'siendo\s+las',
    r'a\s+los'
]

def limpiar_texto_fechas(texto):
    if not texto:
        return ""
    # 1. Reemplazar doble slash por slash simple: 01//01//2024 -> 01/01/2024
    texto = re.sub(r'/{2,}', '/', texto)
    # 2. Reemplazar años con punto en el milenio: 2.024 -> 2024, 2.007 -> 2007, 2.021 -> 2021, 1.998 -> 1998
    return re.sub(r'\b(1|2)\.(\d{3})\b', r'\1\2', texto)

def normalizar_fecha(cadena):
    """
    Intenta parsear una cadena de fecha y la devuelve en formato estándar DD/MM/YYYY.
    Retorna None si no es una fecha válida.
    """
    if not cadena or not isinstance(cadena, str):
        return None
    
    cadena = limpiar_texto_fechas(cadena.strip().lower())
    
    # 1. Formatos numéricos: DD/MM/YYYY, DD-MM-YYYY, YYYY-MM-DD
    m_num = re.search(r'\b(\d{1,2})[/\.-](\d{1,2})[/\.-](\d{2,4})\b', cadena)
    if m_num:
        d, m, y = m_num.groups()
        if len(y) == 2:
            y = "20" + y
        d = d.zfill(2)
        m = m.zfill(2)
        try:
            dt = datetime(int(y), int(m), int(d))
            return dt.strftime('%d/%m/%Y')
        except ValueError:
            pass

    # Formato ISO YYYY-MM-DD
    m_iso = re.search(r'\b(\d{4})[/\.-](\d{1,2})[/\.-](\d{1,2})\b', cadena)
    if m_iso:
        y, m, d = m_iso.groups()
        d = d.zfill(2)
        m = m.zfill(2)
        try:
            dt = datetime(int(y), int(m), int(d))
            return dt.strftime('%d/%m/%Y')
        except ValueError:
            pass

    # 2. Formatos textuales
    for mes_nombre, mm in MESES_ES.items():
        m_text = re.search(rf'\b(\d{{1,2}})\b[^\d]{{1,30}}\b({mes_nombre})\b[^\d]{{1,30}}\b(\d{{2,4}})\b', cadena, re.IGNORECASE)
        if m_text:
            d, ano = m_text.group(1), m_text.group(3)
            if len(ano) == 2:
                ano = "20" + ano
            d = d.zfill(2)
            try:
                dt = datetime(int(ano), int(mm), int(d))
                return dt.strftime('%d/%m/%Y')
            except ValueError:
                pass

    return None

def extraer_todas_las_fechas(texto):
    """
    Escanea todo el texto del documento y extrae una lista de fechas únicas en formato DD/MM/YYYY.
    """
    if not texto:
        return []
    
    fechas_encontradas = set()
    texto_clean = limpiar_texto_fechas(texto.replace('\n', ' '))

    # 1. Buscar patrones numéricos: DD/MM/YYYY, DD-MM-YYYY
    patrones_num = re.findall(r'\b\d{1,2}[/\.-]\d{1,2}[/\.-]\d{2,4}\b', texto_clean)
    for p in patrones_num:
        f_norm = normalizar_fecha(p)
        if f_norm:
            fechas_encontradas.add(f_norm)

    # 2. Buscar patrones YYYY-MM-DD
    patrones_iso = re.findall(r'\b\d{4}[/\.-]\d{1,2}[/\.-]\d{1,2}\b', texto_clean)
    for p in patrones_iso:
        f_norm = normalizar_fecha(p)
        if f_norm:
            fechas_encontradas.add(f_norm)

    # 3. Buscar patrones textuales con flexibilidad OCR
    for mes_nombre, mm in MESES_ES.items():
        matches = re.finditer(rf'\b(\d{{1,2}})\b[^\d]{{1,30}}\b({mes_nombre})\b[^\d]{{1,30}}\b(\d{{2,4}})\b', texto_clean, re.IGNORECASE)
        for m in matches:
            dia, ano = m.group(1), m.group(3)
            if len(ano) == 2:
                ano = "20" + ano
            dia = dia.zfill(2)
            try:
                dt = datetime(int(ano), int(mm), int(dia))
                fechas_encontradas.add(dt.strftime('%d/%m/%Y'))
            except ValueError:
                pass

    return sorted(list(fechas_encontradas))

def extraer_fecha_expedicion_semantica(texto):
    """
    Analiza semánticamente el texto e identifica la Fecha Real de Expedición/Celebración.
    Filtra cierres contables (ej. 31/12/YYYY).
    Retorna: (fecha_expedicion: str o None, todas_las_fechas: list[str])
    """
    todas = extraer_todas_las_fechas(texto)
    if not todas:
        return None, []

    texto_clean = limpiar_texto_fechas(texto.replace('\n', ' '))

    # 1. Buscar fechas asociadas semánticamente a verbos de expedición/celebración
    candidatas_ancladas = []
    for anclaje in ANCLAJES_EXPEDICION:
        matches = re.finditer(rf'{anclaje}[^.]{{0,60}}', texto_clean, re.IGNORECASE)
        for m in matches:
            fragmento = m.group(0)
            fechas_frag = extraer_todas_las_fechas(fragmento)
            for f in fechas_frag:
                if not f.startswith("31/12/"):
                    candidatas_ancladas.append(f)

    if candidatas_ancladas:
        return candidatas_ancladas[0], todas

    # 2. Fallback: Filtrar fechas contables de cierre de ejercicio (31/12/YYYY)
    no_contables = [f for f in todas if not f.startswith("31/12/")]
    if no_contables:
        return no_contables[-1], todas

    return todas[0] if todas else None, todas

def validar_coincidencia_fecha(fecha_indice_raw, texto_documento):
    """
    Compara la fecha del índice contra la fecha detectada en el documento.
    Si difieren, retorna la alerta simple y limpia: "Operador dijo X, IA detectó Y".
    """
    fecha_expedicion, todas_las_fechas = extraer_fecha_expedicion_semantica(texto_documento)
    
    fecha_detectada_ia = fecha_expedicion
    if not fecha_detectada_ia and todas_las_fechas:
        fecha_detectada_ia = todas_las_fechas[0]
    
    if not fecha_detectada_ia:
        fecha_detectada_ia = "No detectada"

    if not fecha_indice_raw or fecha_indice_raw.strip().upper() == 'NULL':
        return True, "N/A", fecha_detectada_ia, "Sin fecha en índice"

    fecha_indice_norm = normalizar_fecha(fecha_indice_raw)
    if not fecha_indice_norm:
        fecha_indice_norm = fecha_indice_raw.strip()

    # Comprobar si coincide
    coincide = (fecha_indice_norm == fecha_detectada_ia) or (fecha_indice_norm in todas_las_fechas)

    if coincide:
        mensaje = f"✅ Fecha Coincide ({fecha_indice_norm})"
        return True, fecha_indice_norm, fecha_indice_norm, mensaje
    else:
        mensaje = f"🚨 DISCREPANCIA FECHA: Operador dijo {fecha_indice_norm}, IA detectó {fecha_detectada_ia}"
        return False, fecha_indice_norm, fecha_detectada_ia, mensaje
