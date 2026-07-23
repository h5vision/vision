const fs = require("fs");
const path = require("path");

const source = path.join(
    __dirname,
    "..",
    "node_modules",
    "@vscode",
    "codicons",
    "dist"
);

const target = path.join(
    __dirname,
    "..",
    "media",
    "codicon"
);

fs.mkdirSync(target, { recursive: true });

// ttf 복사
fs.copyFileSync(
    path.join(source, "codicon.ttf"),
    path.join(target, "codicon.ttf")
);

// css 읽기
let css = fs.readFileSync(
    path.join(source, "codicon.css"),
    "utf8"
);

// 원하는 경로로 수정
css = css.replace(
    /url\(["']?codicon\.ttf["']?\)/g,
    'url("./codicon.ttf")'
);

// 저장
fs.writeFileSync(
    path.join(target, "codicon.css"),
    css,
    "utf8"
);

console.log("✔ Codicon copied and patched.");