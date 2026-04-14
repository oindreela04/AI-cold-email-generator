import streamlit as st

st.title("Cold Email Automation Tool")

st.write("App is running...")  # debug line

role = st.text_input("Target Role")
skills = st.text_area("Your Skills")

if st.button("Generate Emails"):
    st.write("Button clicked")  # debug

    if not role or not skills:
        st.warning("Please fill all fields")
    else:
        st.success("Inputs received")