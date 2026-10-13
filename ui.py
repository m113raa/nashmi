"""ui.py - Streamlit chat UI (RTL Arabic).  Run:  streamlit run ui.py"""
import os
import streamlit as st
import rag

st.set_page_config(page_title="مساعد الأحوال المدنية", page_icon="🪪", layout="centered")
st.markdown("""<style>
  .stApp, .stChatMessage, .stMarkdown, p, li, h1, h2, h3, textarea, input { direction: rtl; text-align: right; }
  code { direction: ltr; }
</style>""", unsafe_allow_html=True)

st.title("🪪 مساعد الأحوال المدنية الذكي")
st.caption("اسأل عن الهوية، تسجيل المواليد، دفتر العائلة، أو ابحث برقم وطني.")

with st.sidebar:
    st.header("الإعدادات")
    data_dir = st.text_input("مجلد البيانات", rag.DATA_DIR)
    if st.button("🔄 إعادة بناء الفهرس"):
        with st.spinner("جاري الفهرسة... (قد تستغرق عدة دقائق)"):
            rag.build_index(data_dir)
        st.cache_resource.clear()
        st.success("تم بناء الفهرس")
    show_ctx = st.checkbox("إظهار السياق المسترجع (للتجربة)", False)
    if st.button("🗑️ محادثة جديدة"):
        st.session_state.messages = []
    st.divider()
    st.caption(f"LLM: {rag.LLM_MODEL}\n\nEmbeddings: {rag.EMB_MODEL}" + ("\n\n⚠️ وضع تجريبي RAG_FAKE" if rag.FAKE else ""))


@st.cache_resource
def get_retriever():
    return rag.Retriever()


if not os.path.exists(rag.INDEX_PATH):
    st.warning("لا يوجد فهرس بعد. اضغط «إعادة بناء الفهرس» من القائمة الجانبية.")
    st.stop()

retriever = get_retriever()
st.session_state.setdefault("messages", [])

if not st.session_state.messages:
    cols = st.columns(3)
    for col, q in zip(cols, ["كم رسوم تجديد الهوية؟", "شو الأوراق المطلوبة لتسجيل مولود؟", "ما ساعات الدوام يوم السبت؟"]):
        if col.button(q):
            st.session_state.pending = q

for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

question = st.chat_input("اكتب سؤالك هنا...") or st.session_state.pop("pending", None)
if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        history = [m for m in st.session_state.messages[:-1]]
        gen, sources, context = rag.answer(retriever, question, history=history, stream=True)
        text = st.write_stream(gen)
        with st.expander("📚 المصادر"):
            for i, s in enumerate(sources, 1):
                st.markdown(f"[{i}] {s}")
            if show_ctx:
                st.text(context)
    st.session_state.messages.append({"role": "assistant", "content": text})
