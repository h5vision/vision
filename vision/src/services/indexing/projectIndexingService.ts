
import { ProjectIndexingData } from "../../types/index";
import { ProjectMetadataService } from "./projectMetadataService";
import { WorkspaceService } from "../workspaceService";
import { DirectoryTreeService } from "./directoryTreeService";


export class ProjectIndexingService {
    private readonly ProjectMetadata = new ProjectMetadataService();
    private readonly workspaceService = new WorkspaceService();
    private readonly directoryTreeService = new DirectoryTreeService();

    public async getProjectIndexingData(): Promise<ProjectIndexingData | void> {
        const workspace = this.workspaceService.getWorkspace();
        let project_id = "";
        if (!workspace) {
            return {
                project_id: 'empty',
                documents: [],
                metadata: {additionalProp1: null}
            };
        }
        else {
            project_id = workspace.name;
            let metadata = await this.ProjectMetadata.getMetadata();
            const dirTree = await this.directoryTreeService.getDirectoryTree(workspace.path);
            const files = this.directoryTreeService.flattenFiles(dirTree);
            files.forEach((obj) => {
                obj.language = obj.name.split('.')[1];
            });
        
            return {
                project_id: project_id,
                documents: files,
                metadata: {
                    additionalProp1: metadata
                }
            };
        }
    };
};