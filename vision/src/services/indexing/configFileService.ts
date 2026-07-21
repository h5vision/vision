import * as fs from "fs";
import * as path from "path";
import { ConfigFiles } from "../../types";

export class ConfigFileService {

    public getConfigFiles(workspacePath: string): ConfigFiles {

        const exists = (file: string) =>
            fs.existsSync(path.join(workspacePath, file));

        return {
            packageJson: exists("package.json"),
            tsconfig: exists("tsconfig.json"),
            readme: exists("README.md"),
            gitignore: exists(".gitignore")
        };
    }
}