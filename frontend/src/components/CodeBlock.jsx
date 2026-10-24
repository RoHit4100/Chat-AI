import React, { useState } from "react";
import Prism from "prismjs";
import "prismjs/themes/prism-tomorrow.css";
import { Check, Copy } from "lucide-react";

export function CodeBlock({ language = "text", value = "" }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const getHighlightedCode = () => {
    const validLang = Prism.languages[language] ? language : "javascript";
    const grammar = Prism.languages[validLang] || Prism.languages.text;
    try {
      return Prism.highlight(value, grammar, validLang);
    } catch {
      return value;
    }
  };

  return (
    <div className="code-block-wrapper">
      <div className="code-block-header">
        <span>{language}</span>
        <button className="copy-btn" onClick={handleCopy} title="Copy code to clipboard">
          {copied ? (
            <>
              <Check size={12} color="#10b981" />
              <span>Copied!</span>
            </>
          ) : (
            <>
              <Copy size={12} />
              <span>Copy</span>
            </>
          )}
        </button>
      </div>
      <pre className="code-pre">
        <code
          className={`language-${language}`}
          dangerouslySetInnerHTML={{ __html: getHighlightedCode() }}
        />
      </pre>
    </div>
  );
}
