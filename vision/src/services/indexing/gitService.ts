import * as fs from "fs";
import * as path from "path";
import { GitMetadata } from "../../types";

export class GitService {

    public getGitInfo(workspacePath: string): GitMetadata {
        const enabled = fs.existsSync(path.join(workspacePath, ".git"));
        if (enabled) {

            
            return {
                enabled: enabled
            };
        } else {
            return {
                enabled: enabled
            };
        }
    }
}