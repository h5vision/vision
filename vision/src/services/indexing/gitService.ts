import * as fs from "fs";
import * as path from "path";
import { GitMetadata } from "../../types";

export class GitService {

    public getGitInfo(workspacePath: string): GitMetadata {

        return {
            enabled: fs.existsSync(path.join(workspacePath, ".git"))
        };
    }
}