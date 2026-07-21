export interface WorkspaceMetadata {
    name: string;
    path: string;
}

export interface ConfigFiles {
    packageJson: boolean;
    tsconfig: boolean;
    readme: boolean;
    gitignore: boolean;
}

export interface GitMetadata {
    enabled: boolean;
}

export interface LanguageMetadata {
    primaryLanguage: string;
}

export interface ProjectMetadata {
    workspace: WorkspaceMetadata;
    vscodeVersion: string;
    isMultiRoot: boolean;
    configFiles: ConfigFiles;
    git: GitMetadata;
    language: LanguageMetadata;
    dirTree: DirectoryNode;
}

export interface ProjectIndexingData {
  project_id: string;
  documents: DirectoryNode[];
  metadata: {
     additionalProp1: ProjectMetadata | null;
  }
}

export interface DirectoryNode {
    name: string;
    path: string;
    type: "file" | "directory";

    language?: string;
    size?: number;
    modifiedTime?: Date;
    children?: DirectoryNode[];
}