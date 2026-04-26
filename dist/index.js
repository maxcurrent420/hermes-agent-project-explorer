/**
 * Project Explorer Dashboard Plugin
 *
 * Displays tracked projects and their file structures.
 * Allows linking sessions to projects.
 */
(function () {
    "use strict";

    const SDK = window.__HERMES_PLUGIN_SDK__;
    const { React } = SDK;
const {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  Badge,
  Button,
  Input,
} = SDK.components;
    const { useState, useEffect, useCallback } = SDK.hooks;
    const { cn, timeAgo } = SDK.utils;

    function ProjectsPage() {
        const [view, setView] = useState("projects");
        const [projects, setProjects] = useState([]);
        const [sessions, setSessions] = useState([]);
        const [selectedProject, setSelectedProject] = useState(null);
        const [projectTree, setProjectTree] = useState(null);
        const [loading, setLoading] = useState(true);
        const [treeLoading, setTreeLoading] = useState(false);
        const [searchQuery, setSearchQuery] = useState("");
        const [error, setError] = useState(null);
        
        const [linkDialogOpen, setLinkDialogOpen] = useState(false);
        const [selectedSession, setSelectedSession] = useState(null);
        const [projectPathInput, setProjectPathInput] = useState("");

        // Collapsible tree state
        const [expandedPaths, setExpandedPaths] = useState(new Set());

        const toggleFolder = useCallback(function(path) {
            setExpandedPaths(function(prev) {
                var next = new Set(prev);
                if (next.has(path)) {
                    next.delete(path);
                } else {
                    next.add(path);
                }
                return next;
            });
        }, []);

        var resetExpandedPaths = useCallback(function() {
            setExpandedPaths(new Set());
        }, []);

        const fetchProjects = useCallback(function () {
            setLoading(true);
            setError(null);
            SDK.fetchJSON("/api/plugins/project-explorer/projects")
                .then(function (data) {
                    setProjects(data.projects || []);
                })
                .catch(function (err) {
                    setError("Failed to load projects");
                    console.error(err);
                })
                .finally(function () {
                    setLoading(false);
                });
        }, []);

const fetchSessions = useCallback(function () {
  SDK.api.getSessions(20)
    .then(function (resp) {
      setSessions(resp.sessions || []);
    })
    .catch(function (err) {
      console.error("Failed to load sessions:", err);
      setSessions([]);
    });
}, []);

        const fetchProjectTree = useCallback(function (projectId) {
            setTreeLoading(true);
            SDK.fetchJSON("/api/plugins/project-explorer/projects/" + projectId + "/tree?depth=5")
                .then(function (data) {
                    setProjectTree(data.tree);
                })
                .catch(function (err) {
                    console.error("Failed to load tree:", err);
                    setProjectTree(null);
                })
                .finally(function () {
                    setTreeLoading(false);
                });
        }, []);

        useEffect(function () {
            fetchProjects();
            fetchSessions();
        }, [fetchProjects, fetchSessions]);

        useEffect(function () {
            if (selectedProject) {
                fetchProjectTree(selectedProject.id);
                resetExpandedPaths();
            } else {
                setProjectTree(null);
            }
        }, [selectedProject, fetchProjectTree, resetExpandedPaths]);

        var filteredProjects = projects;
        if (searchQuery) {
            var query = searchQuery.toLowerCase();
            filteredProjects = projects.filter(function (p) {
                return p.name.toLowerCase().includes(query) || p.path.toLowerCase().includes(query);
            });
        }

        function handleLinkSession(session) {
            setSelectedSession(session);
            setProjectPathInput(session.cwd || "");
            setLinkDialogOpen(true);
        }

        function submitLinkProject() {
            if (!projectPathInput.trim()) return;
            
            SDK.fetchJSON("/api/plugins/project-explorer/sessions/" + selectedSession.id + "/link", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ project_path: projectPathInput.trim() })
            })
            .then(function (data) {
                setLinkDialogOpen(false);
                setSelectedSession(null);
                setProjectPathInput("");
                fetchProjects();
                if (data.project) {
                    setSelectedProject(data.project);
                }
            })
            .catch(function (err) {
                console.error("Failed to link project:", err);
                alert("Failed to link project: " + err.message);
            });
        }

        function renderTreeNode(node, depth) {
            if (!node) return null;
            var indent = depth * 16;
            var isDir = node.type === "directory";

            // For directories, check if expanded
            var isExpanded = isDir && node.path && expandedPaths.has(node.path);
            var hasChildren = isDir && node.children && node.children.length > 0;

            var containerStyle = {
                paddingLeft: indent + "px"
            };

            if (isDir) {
                // Directory row - clickable to toggle
                var row = React.createElement("div", {
                    className: cn(
                        "flex items-center gap-1 py-1 text-sm font-medium cursor-pointer hover:bg-foreground/5 rounded px-1",
                        isExpanded && "bg-foreground/5"
                    ),
                    style: containerStyle,
                    onClick: function(e) {
                        e.stopPropagation();
                        if (node.path) {
                            toggleFolder(node.path);
                        }
                    }
                },
                    // Chevron indicator
                    React.createElement("span", {
                        className: cn(
                            "w-4 text-xs text-muted-foreground transition-transform",
                            isExpanded ? "rotate-90" : ""
                        ),
                        style: { display: "inline-block", width: 16 }
                    }, hasChildren ? (isExpanded ? "▼" : "▶") : " "),
                    React.createElement("span", { className: "text-amber-500" }, "\uD83D\uDCC1"),
                    React.createElement("span", null, node.name),
                    hasChildren && React.createElement("span", { className: "text-xs text-muted-foreground ml-1" },
                        "(" + node.children.length + ")"
                    )
                );

                // Render children only if expanded
                if (isExpanded && node.children) {
                    var childrenDiv = React.createElement("div", { className: "" },
                        node.children.map(function(child) {
                            return renderTreeNode(child, depth + 1);
                        })
                    );
                    return React.createElement(React.Fragment, { key: node.path || node.name },
                        row,
                        childrenDiv
                    );
                }

                return row;
            } else {
                // File row - non-clickable
                return React.createElement("div", {
                    key: node.path || node.name,
                    className: cn("flex items-center gap-1 py-1 text-sm text-muted-foreground"),
                    style: containerStyle
                },
                    React.createElement("span", { className: "w-4" }, " "),
                    React.createElement("span", { className: "text-blue-500" }, "\uD83D\uDCC4"),
                    React.createElement("span", null, node.name)
                );
            }
        }

        function formatLastUsed(timestamp) {
            if (!timestamp) return "Never";
            return timeAgo(timestamp * 1000);
        }

        function renderProjectsView() {
            return React.createElement("div", { className: "flex flex-col h-full gap-4" },
                React.createElement("div", { className: "flex items-center justify-between" },
                    React.createElement("div", { className: "flex items-center gap-3" },
                        React.createElement(CardTitle, { className: "text-xl" }, "Projects"),
                        React.createElement(Badge, { variant: "outline" }, projects.length + " projects")
                    ),
                    React.createElement("div", { className: "flex gap-2" },
                        React.createElement(Input, {
                            placeholder: "Search projects...",
                            value: searchQuery,
                            onChange: function (e) { setSearchQuery(e.target.value); },
                            className: "w-64"
                        }),
                        React.createElement(Button, {
                            variant: "outline",
                            size: "sm",
                            onClick: fetchProjects
                        }, "Refresh")
                    )
                ),

                error && React.createElement(Card, { className: "border-red-500" },
                    React.createElement(CardContent, { className: "py-4" },
                        React.createElement("span", { className: "text-red-500" }, error)
                    )
                ),

                loading && React.createElement(Card,
                    React.createElement(CardContent, { className: "py-8 text-center text-muted-foreground" },
                        "Loading projects..."
                    )
                ),

                !loading && React.createElement("div", { className: "flex flex-1 gap-4 min-h-0" },
                    React.createElement(Card, { className: "w-72 flex flex-col" },
                        React.createElement(CardHeader, { className: "pb-2" },
                            React.createElement(CardTitle, { className: "text-sm" }, "All Projects")
                        ),
                        React.createElement(CardContent, { className: "flex-1 overflow-auto p-0" },
                            filteredProjects.length === 0
                                ? React.createElement("div", { className: "p-4 text-sm text-muted-foreground" },
                                    searchQuery ? "No projects match your search" : "No projects yet. Click Sessions to link a session to a project."
                                )
                                : React.createElement("div", { className: "flex flex-col" },
                                    filteredProjects.map(function (project) {
                                        return React.createElement("button", {
                                            key: project.id,
                                            onClick: function () { setSelectedProject(project); },
                                            className: cn(
                                                "text-left p-3 border-b border-border hover:bg-foreground/5 transition-colors",
                                                selectedProject && selectedProject.id === project.id && "bg-foreground/10"
                                            )
                                        },
                                            React.createElement("div", { className: "font-medium text-sm" }, project.name),
                                            React.createElement("div", { className: "text-xs text-muted-foreground truncate" }, project.path),
                                            React.createElement("div", { className: "flex items-center gap-2 mt-1" },
                                                React.createElement("span", { className: "text-xs text-muted-foreground" },
                                                    formatLastUsed(project.last_used)
                                                ),
                                                project.is_git_repo && React.createElement(Badge, { variant: "secondary", className: "text-xs py-0" }, "Git")
                                            )
                                        );
                                    })
                                )
                        )
                    ),

                    React.createElement(Card, { className: "flex-1 flex flex-col" },
                        selectedProject
                            ? React.createElement(React.Fragment, null,
                                React.createElement(CardHeader, { className: "pb-2" },
                                    React.createElement("div", { className: "flex items-center justify-between" },
                                        React.createElement(CardTitle, { className: "text-lg" }, selectedProject.name),
                                        React.createElement("div", { className: "flex gap-2" },
                                            React.createElement(Button, {
                                                variant: "outline",
                                                size: "sm",
                                                onClick: function () { fetchProjectTree(selectedProject.id); }
                                            }, "Refresh")
                                        )
                                    )
                                ),
                                React.createElement(CardContent, { className: "flex-1 overflow-auto" },
                                    React.createElement("div", { className: "mb-4 p-3 bg-muted/30 rounded-md" },
                                        React.createElement("div", { className: "text-sm font-mono mb-2" }, selectedProject.path),
                                        React.createElement("div", { className: "flex gap-4 text-xs text-muted-foreground" },
                                            React.createElement("span", null, "Sessions: " + selectedProject.session_count),
                                            selectedProject.is_git_repo && React.createElement("span", null, "Git: " + (selectedProject.git_remote || "detected")),
                                            React.createElement("span", null, "Last used: " + formatLastUsed(selectedProject.last_used))
                                        )
                                    ),
                                    treeLoading
                                        ? React.createElement("div", { className: "text-sm text-muted-foreground" }, "Loading tree...")
                                        : projectTree
                                            ? React.createElement("div", { className: "font-mono text-sm" },
                                                renderTreeNode(projectTree, 0)
                                            )
                                            : React.createElement("div", { className: "text-sm text-muted-foreground" },
                                                "Unable to load project tree"
                                            )
                                )
                            )
                            : React.createElement(CardContent, { className: "flex-1 flex items-center justify-center text-muted-foreground" },
                                "Select a project to view its structure"
                            )
                    )
                )
            );
        }

        function renderSessionsView() {
            return React.createElement("div", { className: "flex flex-col h-full gap-4" },
                React.createElement("div", { className: "flex items-center justify-between" },
                    React.createElement("div", { className: "flex items-center gap-3" },
                        React.createElement(CardTitle, { className: "text-xl" }, "Sessions"),
                        React.createElement(Badge, { variant: "outline" }, sessions.length + " active")
                    ),
                    React.createElement(Button, {
                        variant: "outline",
                        size: "sm",
                        onClick: fetchSessions
                    }, "Refresh")
                ),

                React.createElement(Card, { className: "flex-1" },
                    React.createElement(CardContent, { className: "p-0" },
                        sessions.length === 0
                            ? React.createElement("div", { className: "p-4 text-sm text-muted-foreground" },
                                "No active sessions. Start a session from the CLI or gateway to link it to a project."
                            )
                            : React.createElement("div", { className: "flex flex-col" },
                                sessions.map(function (session) {
                                    return React.createElement("div", {
                                        key: session.id,
                                        className: "flex items-center justify-between p-3 border-b border-border"
                                    },
                                        React.createElement("div", { className: "flex-1" },
                                            React.createElement("div", { className: "font-medium text-sm" },
                                                session.title || session.id.substring(0, 8)
                                            ),
                                            React.createElement("div", { className: "text-xs text-muted-foreground" },
                                                session.cwd || "No working directory"
                                            )
                                        ),
                                        React.createElement(Button, {
                                            size: "sm",
                                            onClick: function () { handleLinkSession(session); }
                                        }, "Link to Project")
                                    );
                                })
                            )
                    )
                ),

                React.createElement("div", { className: "text-sm text-muted-foreground" },
                    "Click 'Link to Project' to associate a session with a repository. The project will be tracked and its file structure will be available."
                )
            );
        }

        return React.createElement("div", { className: "flex flex-col h-full" },
            React.createElement("div", { className: "flex gap-2 mb-4" },
                React.createElement(Button, {
                    variant: view === "projects" ? "default" : "outline",
                    size: "sm",
                    onClick: function () { setView("projects"); }
                }, "Projects"),
                React.createElement(Button, {
                    variant: view === "sessions" ? "default" : "outline",
                    size: "sm",
                    onClick: function () { setView("sessions"); }
                }, "Sessions")
            ),

view === "projects" ? renderProjectsView() : renderSessionsView(),

  linkDialogOpen && React.createElement("div", {
    className: "fixed inset-0 bg-black/50 flex items-center justify-center z-50",
    onClick: function (e) { if (e.target === e.currentTarget) setLinkDialogOpen(false); }
  },
    React.createElement("div", {
      className: "bg-background border border-border rounded-lg shadow-lg w-full max-w-md mx-4",
      onClick: function (e) { e.stopPropagation(); }
    },
      React.createElement("div", { className: "p-4 border-b border-border" },
        React.createElement("h2", { className: "text-lg font-semibold" }, "Link Session to Project"),
        React.createElement("p", { className: "text-sm text-muted-foreground mt-1" }, "Enter the root directory path of the project this session is working on.")
      ),
      React.createElement("form", {
        onSubmit: function (e) { e.preventDefault(); submitLinkProject(); },
        className: "p-4"
      },
        React.createElement(Input, {
          placeholder: "/path/to/project",
          value: projectPathInput,
          onChange: function (e) { setProjectPathInput(e.target.value); },
          className: "w-full"
        }),
        selectedSession && selectedSession.cwd && React.createElement("div", { className: "mt-2 text-xs text-muted-foreground" }, "Current session cwd: ", selectedSession.cwd),
        React.createElement("div", { className: "flex justify-end gap-2 mt-4" },
          React.createElement(Button, {
            type: "button",
            variant: "outline",
            onClick: function () { setLinkDialogOpen(false); }
          }, "Cancel"),
          React.createElement(Button, {
            type: "submit",
            disabled: !projectPathInput.trim()
          }, "Link Project")
        )
      )
    )
  )
);
}

    window.__HERMES_PLUGINS__.register("project-explorer", ProjectsPage);
})();