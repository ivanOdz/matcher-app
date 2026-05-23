# Matcher App

POC para matchear productos de un CSV contra varias fuentes JSON y comparar
precios entre ellas.

## Correr local
pip install -r requirements.txt
streamlit run app.py

## Uso
1. Subir el CSV de productos (columnas: Producto, Marca, Categoria, Capacidad, Unidades).
2. Subir uno o varios JSON de fuentes (cada record debe tener el campo `sitio`).
3. Tocar Procesar.

## Deploy en Streamlit Community Cloud

1. Push del repo a GitHub (público o privado con acceso de Streamlit).
2. Entrar a https://share.streamlit.io con la cuenta de GitHub.
3. "New app" → elegir repo `matcher-app`, rama `main`, archivo `app.py`.
4. Deploy. Streamlit instala `requirements.txt` y publica una URL pública.
5. Cada push a `main` redeploya automáticamente.

Nota: el deploy en Streamlit Cloud requiere login interactivo del usuario.
