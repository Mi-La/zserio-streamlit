import os
import sys
import re
import io
import shutil
import streamlit as st
from glob import glob
from zipfile import ZipFile

# needed for python code
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr

import zserio

st.set_page_config(layout="wide", page_title="Interactive Zserio", page_icon="./img/zs.png")

def get_package_names(zs):
    m = re.search("package (.*);", zs)
    if m:
        return m.group(1).split(".")
    return ["default"]

def compile(zs, gen_dir, langs, extra_args):
    if not len(zs):
        return False

    package_names = get_package_names(zs)
    zs_path = os.path.join(gen_dir, "zs")
    zs_file_path = os.path.join(*package_names[0:-1], package_names[-1] + ".zs")
    os.makedirs(os.path.join(zs_path, *package_names[0:-1]))
    with open(os.path.join(zs_path, zs_file_path), "w") as zs_file:
        zs_file.write(zs)

    args=[]
    args+=extra_args
    args+=["-src", zs_path]
    args.append(zs_file_path)
    for lang in langs:
        args+=["-" + lang, os.path.join(gen_dir, lang)]

    completed_process = zserio.run_compiler(args)
    if completed_process.returncode != 0:
        st.error(completed_process.stderr)
        return False

    return True

def recompile_params_changed(zs, checked_langs, extra_args):
    recompile_params = (zs, checked_langs, extra_args)
    if not "recompile_params" in st.session_state or st.session_state.recompile_params != recompile_params:
        st.session_state.recompile_params = recompile_params
        return True
    return False

def recompile(zs, gen_dir, checked_langs, extra_args):
    if recompile_params_changed(zs, checked_langs, extra_args):
        shutil.rmtree(gen_dir, ignore_errors=True)
        with st.spinner("Compiling..."):
            if not compile(zs, gen_dir, checked_langs, extra_args):
                st.stop()
    else:
        st.info("No recompilation needed...")

def map_highlighting(lang):
    if lang == "doc":
        return "html"
    if lang == "cpp":
        # see: https://discuss.streamlit.io/t/c-markdown-syntax-highlighting-doesnt-work/14106/2
        # streamlit seems to have problems with c++ / cpp / cxx
        return "c"
    return lang

def display_sources(gen_dir, lang):
    st.caption(lang)
    generated = glob(gen_dir + "/" + lang + "/**", recursive=True)
    for gen in generated:
        if os.path.isfile(gen):
            with open(gen, "r") as source:
                with st.expander(gen):
                    st.code(source.read(), map_highlighting(lang))

def add_download(gen_dir):
    zip_filename = "gen.zip"
    zip_path = os.path.join(gen_dir, zip_filename)
    if os.path.exists(zip_path):
        os.remove(zip_path)

    files_to_zip = []
    for root, dirs, files in os.walk(gen_dir):
        for f in files:
            files_to_zip.append(os.path.join(root, f))
    with ZipFile(zip_path, "w") as zip_file:
        for f in files_to_zip:
            zip_file.write(f)

    with open(zip_path, "rb") as zip_file:
        st.download_button("Download sources", zip_file, mime="application/zip")

st.write("""
# Interactive Zserio Compiler!
""")

st.session_state.sample_mode = False

uploaded_schema = st.file_uploader("Upload schema", type="zs")
if uploaded_schema:
    st.session_state.sample_mode = False
    schema = uploaded_schema.getvalue().decode("utf8")
    uploaded_schema.close()
else:
    with open("sample_src/sample.zs", "r") as sample:
        st.session_state.sample_mode = True
        schema = sample.read()

zs = st.text_area("Zserio Schema", value=schema, height=150)

extra_args = st.text_input("Extra Arguments").split()

langs = (
    "python", "cpp", "java", "xml", "doc"
)

langs_cols = st.columns(len(langs))

langs_checks = []
for i, lang in enumerate(langs):
    with langs_cols[i]:
        langs_checks.append(st.checkbox(lang, value=(lang == "python")))

checked_langs = []
for i, checked in enumerate(langs_checks):
    if checked:
        checked_langs.append(langs[i])

gen_dir = "gen"
recompile(zs, gen_dir, checked_langs, extra_args)

if len(checked_langs):
    cols = st.columns(len(checked_langs))
    for i, lang in enumerate(checked_langs):
        with cols[i]:
            display_sources(gen_dir, lang)
    add_download(gen_dir)

python_code_check = st.checkbox("Experimental python code", help="Python generator must be enabled", value=True)

if python_code_check and "python" in checked_langs:
    sys.dont_write_bytecode = True
    gen_path = os.path.join(gen_dir, "python")
    if sys.path[-1] != gen_path:
        sys.path.append(gen_path)

    modules_keys = set(sys.modules.keys())

    if st.session_state.sample_mode:
        with open("sample_src/sample.py", "r") as sample:
            py_code = sample.read()
    else:
        py_code = ""

    py_code = st.text_area("Python code", value=py_code, height=250)

    with StringIO() as out, redirect_stdout(out):
        st.caption("Python output")
        try:
            exec(py_code)
            st.text(out.getvalue())
        except Exception as e:
            st.error(e)

    # allow to reload modules imported by the python code
    new_modules_keys = set(sys.modules.keys())
    modules_to_remove = new_modules_keys - modules_keys
    for module_to_remove in modules_to_remove:
        sys.modules.pop(module_to_remove)
