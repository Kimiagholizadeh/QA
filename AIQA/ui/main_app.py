

import streamlit as st
st.set_page_config(page_title="AI Game Tester", layout="centered")
st.title("AI QA ")
st.write("Pick a product to test:")
st.page_link("pages/1_edgelabs_gen2.py", label=" EdgeLabs Gen 2")
st.caption("Add more products by creating more files in ui/pages/.")
