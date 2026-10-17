import streamlit as st

import customer

BADGE = {"in_stock": "🟢 In stock", "low_stock": "🟡 Only a few left", "out_of_stock": "🔴 Out of stock"}
CHIPS = ["Do you have oat milk?", "What can I get for a barbecue under $20?",
         "I want sparkling water", "Something sweet under $5"]


def render(get_client) -> None:
    st.title("🛒 StockSense Market")
    st.caption("Fresh groceries, with honest availability.")
    tab_shop, tab_chat = st.tabs(["Shop", "Ask our assistant"])

    with tab_shop:
        items = customer.catalog()
        cats = ["All"] + sorted({p["category"] for p in items})
        cat = st.radio("Category", cats, horizontal=True)
        shown = [p for p in items if cat in ("All", p["category"])]
        for row in range(0, len(shown), 3):
            for col, p in zip(st.columns(3), shown[row : row + 3]):
                with col.container(border=True):
                    st.markdown(f"**{p['name']}**")
                    st.caption(p["category"])
                    st.markdown(f"### ${p['price']:.2f}")
                    st.write(BADGE[p["status"]])
                    if p["status"] == "out_of_stock":
                        st.caption(f"Restock: {p['restock']}")

    with tab_chat:
        hist = st.session_state.setdefault("shop_chat", [])
        picked = None
        for col, s in zip(st.columns(len(CHIPS)), CHIPS):
            if col.button(s, key=f"chip-{s}", width="stretch"):
                picked = s
        for role, text in hist:
            st.chat_message(role).write(text)
        msg = st.chat_input("Ask about products, prices or what to buy") or picked
        if msg:
            st.chat_message("user").write(msg)
            try:
                with st.spinner("Checking the shelves..."):
                    reply = customer.ask(get_client(), msg, hist)
            except Exception:
                reply = "Sorry, our assistant is unavailable right now. You can still browse the Shop tab."
            st.chat_message("assistant").write(reply)
            hist += [("user", msg), ("assistant", reply)]
