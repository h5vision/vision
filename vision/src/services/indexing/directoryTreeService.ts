import * as fs from "fs/promises";
import * as path from "path";

import { DirectoryNode } from "../../types/index";

export class DirectoryTreeService {
    private readonly ignoredDirectories = [".git", ".vscode", "node_modules", "dist", "build", "out", "coverage" ];
    
    /**
     * 프로젝트 전체 디렉터리 트리 생성
     */
    public async getDirectoryTree(rootPath: string): Promise<DirectoryNode> {

        return await this.readDirectory(rootPath);
    }

    /**
     * 재귀적으로 디렉터리를 탐색
     */
    private async readDirectory(
        currentPath: string
    ): Promise<DirectoryNode> {

        const stat = await fs.stat(currentPath);

        const node: DirectoryNode = {
            name: path.basename(currentPath),
            path: currentPath,
            type: stat.isDirectory()
                ? "directory"
                : "file"
        };

        if (!stat.isDirectory()) {
            return node;
        }

        const entries = await fs.readdir(currentPath);

        const children = await Promise.all(

            entries.map(async (entry) => {

                if (this.ignoredDirectories.includes(entry)) {
                    return null;
                }

                const fullPath = path.join(currentPath, entry);

                return this.readDirectory(fullPath);

            })

        );

        node.children = children.filter(
            (child): child is DirectoryNode => child !== null
        );

        return node;

    }
}