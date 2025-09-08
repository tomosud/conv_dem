# EXR Heightmap Viewer Implementation Plan

## Overview
Create a GitHub Pages compatible heightmap viewer that displays EXR files as 3D displaced meshes with lighting.

## Technical Requirements
- **Framework**: Vanilla HTML/CSS/JavaScript (GitHub Pages compatible)
- **3D Rendering**: Three.js
- **File Format**: EXR files containing heightmap data
- **Grid Resolution**: 1024x1024 base grid with 1m/5m toggle
- **Input Method**: Drag & drop interface

## Architecture

### 1. File Handling
- Drag & drop zone for EXR files
- EXR file parsing (using existing JavaScript libraries)
- Extract height data and resolution information
- Data validation and error handling

### 2. Data Processing
- Read EXR dimensions and height values (meters)
- Resample to 1024x1024 grid maintaining aspect ratio
- Generate vertex positions based on height data
- Support for 1m and 5m grid spacing toggle

### 3. 3D Rendering (Three.js)
- **Geometry**: PlaneGeometry with displaced vertices
- **Material**: Phong/Lambert material with proper normals
- **Lighting**: Directional light + ambient light
- **Camera**: Orbit controls for navigation
- **Scene**: Proper scaling and positioning

### 4. User Interface
- File drop area with visual feedback
- Grid resolution toggle (1m/5m)
- Loading progress indicator
- Basic camera controls information

## File Structure
```
├── index.html          # Main HTML file
├── js/
│   ├── main.js          # Main application logic
│   ├── exr-loader.js    # EXR file parsing
│   └── mesh-generator.js # 3D mesh creation
├── css/
│   └── style.css        # Styling
└── lib/
    ├── three.min.js     # Three.js library
    ├── OrbitControls.js # Camera controls
    └── exr-parser.js    # EXR parsing library
```

## Implementation Steps
1. Set up basic HTML structure with Three.js
2. Implement drag & drop file handling
3. Add EXR file parsing capability
4. Create mesh generation from height data
5. Implement lighting and materials
6. Add camera controls and UI
7. Implement grid resolution toggle
8. Performance optimization and testing

## Key Considerations
- **Performance**: Large EXR files need efficient processing
- **Memory**: 1024x1024 grid = ~1M vertices, optimize for browser limits
- **Compatibility**: Use CDN libraries for GitHub Pages
- **Error Handling**: Graceful handling of invalid/large files
- **User Experience**: Clear feedback during processing

## Sample File Integration
- Test with provided sample: `FG-GML-523506-DEM1A-20250606_resized.exr`
- Handle large file sizes with progress indication
- Validate height data format and range