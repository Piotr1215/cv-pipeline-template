\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{my_cv}[2024/11/01 Modern CV Class]
\LoadClass{article}

\RequirePackage{xcolor}
\RequirePackage{tikz}
\RequirePackage{fontspec}

% Define colors
\definecolor{flashyGreen}{RGB}{0, 255, 127}
\definecolor{lavenderBlue}{RGB}{204, 204, 255}

% Badge command
\newcommand{\badge}[2]{%
    \tikz[baseline=(char.base)]{
        \node[shape=rectangle, fill=#1, rounded corners=3pt, inner sep=2pt, text=black] (char) {\small #2};
    }%
}

% Horizontal rule command
\newcommand{\xhrulefill}[2]{%
    \leavevmode\leaders\hrule height #2 depth 0pt\hfill\kern0pt
}

% Header section
\newcommand{\headerSection}[1]{%
    #1
}

% CV paragraph
\newcommand{\cvParagraph}[1]{%
    #1
}

% CV section
\newcommand{\cvSection}[1]{%
    \vspace{0.5em}
    {\Large\textbf{#1}}
    \vspace{0.3em}
    \hrule
    \vspace{0.5em}
}

% Position and company line
\newcommand{\positionAndCompanyLine}[3]{%
    \textbf{#1} \ifx&#2&\else at \textit{#2}\fi \ifx&#3&\else \hfill #3\fi
    \par
}

% Project
\newcommand{\project}[2]{%
    \textit{#1} -- #2
    \par
}

% Tech stack list
\newcommand{\techStackList}[1]{%
    \textit{Tech stack: #1}
    \par
}
