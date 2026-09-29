
import pymupdf
import re
from collections import defaultdict
import pandas as pd
import streamlit as st

# ============================================================
# CONFIGURACIÓN DE LA PÁGINA
# ============================================================

st.set_page_config(
    page_title="Numerador de facturas",
    page_icon="📄",
    layout="wide"
)

st.title("Numerador de facturas")
st.write("Selecciona una factura PDF para validarla y numerar sus partidas.")

# ============================================================
# PROCESAMIENTO DEL PDF
# ============================================================

def procesar_pdf(pdf_bytes):

    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    resultados = []

    COLUMNAS = {
        "Co.": (0, 15),
        "Product No.": (15, 90),
        "Quantity": (175, 225),
        "Price": (235, 300),
        "Net Amt.": (510, 590)
    }

    # --------------------------------------------------------
    # 1. LEER LAS PARTIDAS DE CADA PÁGINA
    # --------------------------------------------------------

    for numero_pagina, page in enumerate(doc, start=1):

        palabras = page.get_text("words")
        filas = defaultdict(list)

        for word in palabras:
            x0, y0, x1, y1, texto = word[:5]

            centro_y = (y0 + y1) / 2
            grupo_y = round(centro_y / 3) * 3

            filas[grupo_y].append({
                "x0": x0,
                "x1": x1,
                "y1": y1,
                "texto": texto.strip()
            })

        filas_procesadas = []

        for grupo_y, elementos in filas.items():

            fila = {}

            for nombre_columna, (x_min, x_max) in COLUMNAS.items():

                encontrados = [
                    elemento for elemento in elementos
                    if x_min <= (
                        elemento["x0"] + elemento["x1"]
                    ) / 2 < x_max
                ]

                encontrados.sort(key=lambda elemento: elemento["x0"])

                fila[nombre_columna] = " ".join(
                    elemento["texto"] for elemento in encontrados
                ).strip()

            fila["_y"] = grupo_y
            fila["_elementos"] = elementos
            filas_procesadas.append(fila)

        filas_partida = []
        filas_solo_producto = []

        # ----------------------------------------------------
        # 2. IDENTIFICAR FILAS DE PARTIDA Y CÓDIGOS SEPARADOS
        # ----------------------------------------------------

        for fila in filas_procesadas:

            pais = fila["Co."].upper()
            np = fila["Product No."]
            cantidad = fila["Quantity"]
            precio = fila["Price"]
            neto = fila["Net Amt."]

            es_pais = re.fullmatch(r"[A-Z]{2}", pais) is not None

            tiene_np = (
                re.search(r"[A-Za-z]", np) is not None
                and re.search(r"\d", np) is not None
            )

            tiene_cantidad = (
                re.fullmatch(r"\d+(?:[.,]\d+)?", cantidad) is not None
            )

            tiene_precio = re.search(r"\d", precio) is not None
            tiene_neto = re.search(r"\d", neto) is not None

            if es_pais and tiene_cantidad and tiene_precio and tiene_neto:

                elemento_co = next(
                    (
                        elemento for elemento in fila["_elementos"]
                        if elemento["texto"].upper() == pais
                        and 0 <= (
                            elemento["x0"] + elemento["x1"]
                        ) / 2 < 15
                    ),
                    None
                )

                if elemento_co is not None:
                    fila["_x_numero"] = elemento_co["x0"]
                    fila["_y_numero"] = elemento_co["y1"]
                    filas_partida.append(fila)

            elif (
                tiene_np
                and not es_pais
                and not cantidad
                and not precio
                and not neto
            ):
                filas_solo_producto.append(fila)

        # ----------------------------------------------------
        # 3. RELACIONAR CÓDIGOS DE PRODUCTO EN OTRA LÍNEA
        # ----------------------------------------------------

        posibles_asignaciones = []

        for indice_partida, fila_partida in enumerate(filas_partida):

            if fila_partida["Product No."]:
                continue

            for indice_producto, fila_producto in enumerate(filas_solo_producto):

                diferencia_y = abs(
                    fila_partida["_y"] - fila_producto["_y"]
                )

                if diferencia_y <= 18:
                    posibles_asignaciones.append((
                        diferencia_y,
                        indice_partida,
                        indice_producto
                    ))

        posibles_asignaciones.sort(key=lambda elemento: elemento[0])

        partidas_asignadas = set()
        productos_asignados = set()

        for diferencia_y, indice_partida, indice_producto in posibles_asignaciones:

            if indice_partida in partidas_asignadas:
                continue

            if indice_producto in productos_asignados:
                continue

            filas_partida[indice_partida]["Product No."] = (
                filas_solo_producto[indice_producto]["Product No."]
            )

            partidas_asignadas.add(indice_partida)
            productos_asignados.add(indice_producto)

        # ----------------------------------------------------
        # 4. GUARDAR PARTIDAS COMPLETAS
        # ----------------------------------------------------

        for fila in filas_partida:

            pais = fila["Co."].upper()
            np = fila["Product No."]
            cantidad = fila["Quantity"]
            precio = fila["Price"]
            neto = fila["Net Amt."]

            es_pais = re.fullmatch(r"[A-Z]{2}", pais) is not None

            tiene_np = (
                re.search(r"[A-Za-z]", np) is not None
                and re.search(r"\d", np) is not None
            )

            tiene_cantidad = (
                re.fullmatch(r"\d+(?:[.,]\d+)?", cantidad) is not None
            )

            tiene_precio = re.search(r"\d", precio) is not None
            tiene_neto = re.search(r"\d", neto) is not None

            if (
                es_pais
                and tiene_np
                and tiene_cantidad
                and tiene_precio
                and tiene_neto
            ):
                resultados.append({
                    "Página": numero_pagina,
                    "Co.": pais,
                    "Product No.": np,
                    "Quantity": cantidad,
                    "Price": precio,
                    "Net Amt.": neto,
                    "_y": fila["_y"],
                    "_x_numero": fila["_x_numero"],
                    "_y_numero": fila["_y_numero"]
                })

    # --------------------------------------------------------
    # 5. ORDENAR LAS PARTIDAS
    # --------------------------------------------------------

    resultados.sort(key=lambda r: (r["Página"], r["_y"]))

    # --------------------------------------------------------
    # 6. LEER LOS TOTALES IMPRESOS EN LA FACTURA
    # --------------------------------------------------------

    texto_pdf = "\n".join(
        pagina.get_text("text") for pagina in doc
    )

    texto_pdf = re.sub(r"\s+", " ", texto_pdf)

    coincidencia_items = re.search(
        r"\b([\d,]+)\s+ITEMS\b",
        texto_pdf,
        re.IGNORECASE
    )

    coincidencia_units = re.search(
        r"\b([\d,]+)\s+UNITS\b",
        texto_pdf,
        re.IGNORECASE
    )

    if not coincidencia_items:
        doc.close()
        raise ValueError("No se pudo encontrar el total de ITEMS en la factura.")

    if not coincidencia_units:
        doc.close()
        raise ValueError("No se pudo encontrar el total de UNITS en la factura.")

    ITEMS_FACTURA = int(
        coincidencia_items.group(1).replace(",", "")
    )

    UNITS_FACTURA = int(
        coincidencia_units.group(1).replace(",", "")
    )

    # --------------------------------------------------------
    # 7. VALIDAR LOS TOTALES DETECTADOS
    # --------------------------------------------------------

    total_items_detectados = len(resultados)

    total_units_detectados = sum(
        float(r["Quantity"].replace(",", "."))
        for r in resultados
    )

    if total_items_detectados != ITEMS_FACTURA:
        doc.close()
        raise ValueError(
            f"Las partidas detectadas ({total_items_detectados}) "
            f"no coinciden con ITEMS de la factura ({ITEMS_FACTURA}). "
            "No se numeró el PDF."
        )

    if total_units_detectados != UNITS_FACTURA:
        doc.close()
        raise ValueError(
            f"Las unidades calculadas ({total_units_detectados:g}) "
            f"no coinciden con UNITS de la factura ({UNITS_FACTURA}). "
            "No se numeró el PDF."
        )

    # --------------------------------------------------------
    # 8. INSERTAR LA NUMERACIÓN
    # --------------------------------------------------------

    for numero, registro in enumerate(resultados, start=1):

        pagina = doc[registro["Página"] - 1]

        pagina.insert_text(
            pymupdf.Point(
                registro["_x_numero"],
                registro["_y_numero"] + 7
            ),
            str(numero),
            fontsize=10,
            fontname="hebo"
        )

        registro["N.º"] = numero

    # --------------------------------------------------------
    # 9. PREPARAR TABLA Y PDF DE SALIDA
    # --------------------------------------------------------

    columnas_mostrar = [
        "N.º",
        "Página",
        "Co.",
        "Product No.",
        "Quantity",
        "Price",
        "Net Amt."
    ]

    df = pd.DataFrame(resultados)[columnas_mostrar]

    pdf_salida = doc.tobytes()
    doc.close()

    return pdf_salida, df, ITEMS_FACTURA, UNITS_FACTURA, total_units_detectados


# ============================================================
# INTERFAZ DE LA PÁGINA
# ============================================================

archivo = st.file_uploader(
    "Selecciona una factura en formato PDF",
    type=["pdf"]
)

if archivo is not None:

    st.info(f"Archivo seleccionado: {archivo.name}")

    if st.button("Validar y numerar factura", type="primary"):

        try:
            with st.spinner("Procesando factura..."):

                pdf_salida, df, items_esperados, units_esperadas, units_detectadas = (
                    procesar_pdf(archivo.getvalue())
                )

            st.success("Validación correcta. La factura fue numerada.")

            st.write(f"**ITEMS detectados:** {len(df)}")
            st.write(f"**ITEMS esperados:** {items_esperados}")
            st.write(f"**UNITS calculadas:** {units_detectadas:g}")
            st.write(f"**UNITS esperadas:** {units_esperadas}")

            st.subheader("Partidas detectadas")
            st.dataframe(df, use_container_width=True, hide_index=True)

            nombre_salida = archivo.name.rsplit(".", 1)[0] + "_numerado.pdf"

            st.download_button(
                label="Descargar PDF numerado",
                data=pdf_salida,
                file_name=nombre_salida,
                mime="application/pdf"
            )

        except Exception as error:
            st.error(str(error))