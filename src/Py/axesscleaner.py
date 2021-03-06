import argparse
import os.path
import re
import subprocess

import ply.lex
from flatex import expand_file

parser = argparse.ArgumentParser(description='This method takes as inputs ')

parser.add_argument('-i', dest='input',
                    help='Input File (Required). It accepts only .tex files')

parser.add_argument('-o', dest='output', default='',
                    help='Output File (optional, default: input file with _clean as suffix)')

parser.add_argument('-p', dest='pdflatex', action='store_const',
                    const=True, default=False,
                    help='If selected, runs pdflatex at the end')

args = parser.parse_args()




# Usage
# python stripcomments.py input.tex > output.tex
# python stripcomments.py input.tex -e encoding > output.tex

# modified from https://gist.github.com/amerberg/a273ca1e579ab573b499

# Usage
# python stripcomments.py input.tex > output.tex
# python stripcomments.py input.tex -e encoding > output.tex

# Modification:
# 1. Preserve "\n" at the end of line comment
# 2. For \makeatletter \makeatother block, Preserve "%" 
#    if it is actually a comment, and trim the line
#    while preserve the "\n" at the end of the line. 
#    That is because remove the % some time will result in
#    compilation failure.

def strip_comments(source):
    tokens = (
        'PERCENT', 'BEGINCOMMENT', 'ENDCOMMENT',
        'BACKSLASH', 'CHAR', 'BEGINVERBATIM',
        'ENDVERBATIM', 'NEWLINE', 'ESCPCT',
        'MAKEATLETTER', 'MAKEATOTHER',
    )
    states = (
        ('makeatblock', 'exclusive'),
        ('makeatlinecomment', 'exclusive'),
        ('linecomment', 'exclusive'),
        ('commentenv', 'exclusive'),
        ('verbatim', 'exclusive')
    )

    # Deal with escaped backslashes, so we don't
    # think they're escaping %
    def t_BACKSLASH(t):
        r"\\\\"
        return t

    # Leaving all % in makeatblock
    def t_MAKEATLETTER(t):
        r"\\makeatletter"
        t.lexer.begin("makeatblock")
        return t

    # One-line comments
    def t_PERCENT(t):
        r"\%"
        t.lexer.begin("linecomment")

    # Escaped percent signs
    def t_ESCPCT(t):
        r"\\\%"
        return t

    # Comment environment, as defined by verbatim package
    def t_BEGINCOMMENT(t):
        r"\\begin\s*{\s*comment\s*}"
        t.lexer.begin("commentenv")

    # Verbatim environment (different treatment of comments within)
    def t_BEGINVERBATIM(t):
        r"\\begin\s*{\s*verbatim\s*}"
        t.lexer.begin("verbatim")
        return t

    # Any other character in initial state we leave alone
    def t_CHAR(t):
        r"."
        return t

    def t_NEWLINE(t):
        r"\n"
        return t

    # End comment environment
    def t_commentenv_ENDCOMMENT(t):
        r"\\end\s*{\s*comment\s*}"
        # Anything after \end{comment} on a line is ignored!
        t.lexer.begin('linecomment')

    # Ignore comments of comment environment
    def t_commentenv_CHAR(t):
        r"."
        pass

    def t_commentenv_NEWLINE(t):
        r"\n"
        pass

    # End of verbatim environment
    def t_verbatim_ENDVERBATIM(t):
        r"\\end\s*{\s*verbatim\s*}"
        t.lexer.begin('INITIAL')
        return t

    # Leave contents of verbatim environment alone
    def t_verbatim_CHAR(t):
        r"."
        return t

    def t_verbatim_NEWLINE(t):
        r"\n"
        return t

    # End a % comment when we get to a new line
    def t_linecomment_ENDCOMMENT(t):
        r"\n"
        t.lexer.begin("INITIAL")

        # Newline at the end of a line comment is presevered.
        return t

    # Ignore anything after a % on a line
    def t_linecomment_CHAR(t):
        r"."
        pass

    def t_makeatblock_MAKEATOTHER(t):
        r"\\makeatother"
        t.lexer.begin('INITIAL')
        return t

    def t_makeatblock_BACKSLASH(t):
        r"\\\\"
        return t

    # Escaped percent signs in makeatblock
    def t_makeatblock_ESCPCT(t):
        r"\\\%"
        return t

    # presever % in makeatblock
    def t_makeatblock_PERCENT(t):
        r"\%"
        t.lexer.begin("makeatlinecomment")
        return t

    def t_makeatlinecomment_NEWLINE(t):
        r"\n"
        t.lexer.begin('makeatblock')
        return t

    # Leave contents of makeatblock alone
    def t_makeatblock_CHAR(t):
        r"."
        return t

    def t_makeatblock_NEWLINE(t):
        r"\n"
        return t

    # For bad characters, we just skip over it
    def t_ANY_error(t):
        t.lexer.skip(1)

    lexer = ply.lex.lex()
    lexer.input(source)
    return u"".join([tok.value for tok in lexer])


START_PATTERN = 'egin{document}'
END_PATTERN = 'nd{document}'

MACRO_DICTIONARY = []


def gather_macro(strz):
    """
        This method searches for defs, newcommands, edef, gdef,xdef, DeclareMathOperators and renewcommand
        and gets the macro structure out of it. Number
    """

    subs_regexp = []
    # You can manually specify the number of replacements by changing the 4th argument
    should_parse = True
    # parse preamble
    for i, LINE in enumerate(strz.split('\n')):
        if should_parse:
            if re.search(START_PATTERN, LINE):
                should_parse = False
            else:
                result = parse_macro_structure(LINE)
                if result:
                    # print(result,line)
                    MACRO_DICTIONARY.append(result)
        else:
            if re.search(END_PATTERN, LINE):
                break
            else:
                pass


def get_expanded_macro():
    subs_regexp = []
    for reg in MACRO_DICTIONARY:
        expanded_regexp = build_subs_regexp(reg)
        if expanded_regexp:
            subs_regexp.append(expanded_regexp)
    return subs_regexp


def remove_macro(st, o_file):
    subs_regexp = get_expanded_macro()
    should_substitute = False
    final_doc = []
    for i, LINE in enumerate(st.split('\n')):
        if should_substitute:
            if re.search(END_PATTERN, LINE):
                final_doc.append(LINE)
                break
            else:
                # Perform substitutions
                try:
                    LINE = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\xff]', '', recursive_expansion(LINE, subs_regexp))
                except Exception as e:
                    print(e)
                    print(LINE)
                    break

        else:
            if re.search(START_PATTERN, LINE):
                should_substitute = True
            else:
                pass
        if not LINE.isspace():
            final_doc.append(LINE)
    with open(o_file, 'w') as o:
        for final_line in final_doc:
            if final_line.rstrip():
                o.write(final_line + '\n')


def parse_macro_structure(ln):
    """
    :param ln: a text line
    :return: structure (see below) of the macro inside the line (if any)
    """
    regexp = r"\\(.*command|DeclareMathOperator|def|edef|xdef|gdef)({|)(\\[a-zA-Z]+)(}|)(\[([0-9])\]|| +){(.*(?=\}))\}.*$"
    result = re.search(regexp, ln)
    if result:
        regex = r"\\([[:blank:]]|)(?![a-zA-Z])"
        macro_structure = {
            'command_type': result.group(1),
            'macro_name': result.group(3),
            'separator_open': result.group(2),
            'separator_close': result.group(4),
            'number_of_inputs': result.group(6),
            'raw_replacement': re.sub(regex, '', result.group(7)),
        }
        return macro_structure
    else:
        return None


def build_subs_regexp(reg):
    """
        This method creates the replacement text for the macro.
        TODO:
            - extend this to any input macro
            - recursively expand raw_replacements (up to any degree)
            - build tests
    """
    if re.search('declare', reg["command_type"]):

        pass
    else:
        if not reg["number_of_inputs"]:
            # The macro has no inputs
            return {'sub': reg["raw_replacement"], 'reg': '\\' + reg["macro_name"] + '(?![a-zA-Z])', }
        else:
            # The macro has one or more inputs
            pass


def recursive_expansion(lin, available_regexp):
    for subs in available_regexp:
        if not (re.search(subs["reg"], lin)):
            continue
        else:
            try:
                lin = re.sub(subs["reg"], re.sub(r'([\" \' \\\ ])', r'\\\1', subs["sub"]), lin)
            except Exception as e:
                print(e,lin)
    for subs in available_regexp:
        if not (not (re.search(subs["reg"], lin))):
            return recursive_expansion(lin, available_regexp)
        else:
            continue
    return lin


# Begin of actual methods. First check if the input is a LaTex file
if args.input.endswith('.tex'):
    # Check the number of outputs. If no output is given, create a new one.
    if not args.output:
        a = args.input;
        args.output = a.replace('.tex', '_clean.tex')
    # Assign the macro file address and some temporary files.
    FOLDER_PATH = os.path.abspath(os.path.join(os.path.abspath(args.input), os.pardir))
    MACRO_FILE = os.path.join(FOLDER_PATH, "user_macro.sty")
    TEMP_FILE_PRE_EXPANSION = os.path.join(FOLDER_PATH, "temp_pre.tex")

    # Reads the file preamble to obtain the user-defined macros. We also remove unwanted comments.
    print("gather macros from preamble")
    with open(args.input, 'r') as i:
        line = strip_comments(i.read())
        gather_macro(line)
    # Reads user-macro file to obtain the user-defined macros. We also remove unwanted comments
    print("gather macros from user defined file")
    if os.path.exists(MACRO_FILE):
        with open(MACRO_FILE, 'r') as i:
            line = strip_comments(i.read())
            gather_macro(line)
    # Remove the macros from the main file and writes the output to a temp file.
    print("remove macros from main file")
    with open(args.input, 'r') as i:
        line = strip_comments(i.read())
        remove_macro(line, TEMP_FILE_PRE_EXPANSION)

    # Get path of temp file.
    current_path = os.path.split(TEMP_FILE_PRE_EXPANSION)[0]

    # Include all the external files
    print("include external files in main file")
    final_text_to_expand = strip_comments(''.join(expand_file(TEMP_FILE_PRE_EXPANSION, current_path, True, False)))
    # Remove temp file
    os.remove(TEMP_FILE_PRE_EXPANSION)

    # Remove macros from the entire file and put the result to temp file
    print("remove macros from entire file")
    remove_macro(final_text_to_expand, TEMP_FILE_PRE_EXPANSION)

    #get script folder
    script_path = os.path.abspath(os.path.join(__file__, os.pardir))
    preprocess_path =  os.path.join(script_path, "..", "Perl", "AxessibilityPreprocess.pl")
    preprocess_compile_path =  os.path.join(script_path, "..", "Perl", "AxessibilityPreprocesspdfLatex.pl")

    #Call perl scripts to clean dollars, underscores. Eventually, it can call also pdflatex, when -p is selected
    if args.pdflatex:
        print("final cleaning file")
        p = subprocess.Popen(
            ["perl", preprocess_compile_path, "-w", "-o", "-s", TEMP_FILE_PRE_EXPANSION, args.output])
    else:
        print("final cleaning file and pdf production")
        p = subprocess.Popen(
            ["perl", preprocess_path, "-w", "-o", "-s", TEMP_FILE_PRE_EXPANSION, args.output])
    # close process.
    p.communicate()

    # remove spurious file
    os.remove(TEMP_FILE_PRE_EXPANSION)
    os.remove(TEMP_FILE_PRE_EXPANSION.replace('.tex', '.bak'))
else:
    print('The file you inserted as input is not a .tex')
