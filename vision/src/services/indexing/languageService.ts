import * as fs from "fs";
import * as path from "path";
import { LanguageMetadata } from "../../types";

export class LanguageService {

    public getLanguage(workspacePath: string): LanguageMetadata {

        const exists = (file: string) =>
            fs.existsSync(path.join(workspacePath, file));

        if (exists("package.json")) {
            return { primaryLanguage: "TypeScript / JavaScript" };
        }

        if (exists("requirements.txt")) {
            return { primaryLanguage: "Python" };
        }

        if (exists("pom.xml")) {
            return { primaryLanguage: "Java" };
        }

        if (exists("Cargo.toml")) {
            return { primaryLanguage: "Rust" };
        }

        return {
            primaryLanguage: "Unknown"
        };
    }
}