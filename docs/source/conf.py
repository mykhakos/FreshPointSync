import os
import sys

sys.path.insert(0, os.path.abspath('../src'))

project = 'FreshPointSync'
copyright = '2024, Konstantin Mykhailov'
author = 'Konstantin Mykhailov'
release = '0.2.0'


# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'sphinx_rtd_theme',
    'sphinx.ext.autodoc',
    'sphinx.ext.viewcode',
    'sphinx.ext.doctest',
    'sphinx.ext.todo',
    'sphinx.ext.napoleon',
    'sphinxcontrib.autodoc_pydantic',
    'sphinx_copybutton',
]

exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']


# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'sphinx_rtd_theme'
html_static_path = ['_static']
html_logo = '_static/logo_library.svg'
html_theme_options = {
    'logo_only': True,
    'display_version': False,
}

autodoc_typehints = 'description'
autodoc_member_order = 'bysource'
autodoc_default_options = {
    'members': True,
    'undoc-members': True,
    'show-inheritance': True,
}

add_module_names = False


# -- Options for sphinx_copybutton -------------------------------------------
copybutton_prompt_text = r'>>> |\.\.\. |\$ '
copybutton_prompt_is_regexp = True
