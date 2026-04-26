# Project Explorer Plugin

A Hermes Agent dashboard plugin for tracking projects and linking coding sessions to repositories.

## Features

- **Project Tracking**: Automatically discover and track projects from coding sessions
- **File Browser**: Browse file structures from your sessions
- **Session Linking**: Link your coding sessions to their respective repositories
- **Dashboard Tab**: Dedicated "Projects" tab in the Hermes Agent dashboard

## Installation

1. Copy the `project-explorer` folder to your Hermes Agent plugins directory:
   ```bash
   cp -r project-explorer ~/.hermes/hermes-agent/plugins/
   ```

2. Restart Hermes Agent to load the plugin

## Usage

- Navigate to the **Projects** tab in the dashboard
- Projects are automatically discovered from your coding sessions
- Click on a project to browse its file structure
- Sessions are linked to their repositories automatically

## Requirements

- Hermes Agent (latest)
- Python 3.11+

## License

MIT License - see LICENSE file for details.