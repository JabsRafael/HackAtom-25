mkdir -p ~/.streamlit

echo "[server]
headless = true
port = $PORT
enableCORS = false

[theme]
primaryColor='#6534d9'
backgroundColor='#1b1b1b'
secondaryBackgroundColor='#343434'
textColor='#FFFFFF'
font='sans serif'
" > ~/.streamlit/config.toml