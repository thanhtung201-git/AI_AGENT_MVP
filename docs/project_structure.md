# Project Structure

## Purpose

This document defines the directory structure of the Purchase Order Extraction AI Agent project.

A clear project structure helps separate responsibilities, improves maintainability, and makes future development easier.

---

## Directory Structure

```text id="y4t7nc"
project/
│
├── backend/
│   ├── agents/
│   ├── api/
│   ├── config/
│   ├── prompts/
│   ├── schemas/
│   ├── services/
│   ├── tools/
│   └── utils/
│
├── frontend/
│
├── docs/
│
├── sample_data/
│
├── outputs/
│
└── tests/
```

---

## backend/

Contains the core application logic.

### agents/

Coordinate the workflow between modules.

Examples:

* Reader Agent
* Extraction Agent
* Validation Agent

---

### api/

REST API endpoints.

Examples:

* Upload Purchase Order
* Get Extraction Result
* Download Excel

---

### config/

Application configuration.

Examples:

* Environment variables
* Model settings
* API keys
* Logging configuration

---

### prompts/

Prompt templates used by the Large Language Model (LLM).

Examples:

* Extraction Prompt
* Validation Prompt
* Normalization Prompt

---

### schemas/

Data model definitions.

Examples:

* Canonical Schema
* Request Schema
* Response Schema

---

### services/

Business logic independent of APIs.

Examples:

* Extraction Service
* Validation Service
* Export Service

---

### tools/

Utility modules that interact with external resources.

Examples:

* PDF Reader
* OCR
* Excel Reader
* LLM Client
* Excel Generator

---

### utils/

Reusable helper functions.

Examples:

* Date formatting
* Text cleaning
* File utilities
* Logging helpers

---

## frontend/

User interface for interacting with the AI Agent.

Possible features:

* Upload Purchase Order
* View extracted data
* Review validation results
* Download Excel output

---

## docs/

Project documentation.

Includes:

* Problem Statement
* Business Process
* Input / Output Analysis
* Canonical Schema
* System Design

---

## sample_data/

Sample documents used for development and testing.

Examples:

* Purchase Orders
* Ground Truth JSON
* Expected Excel Output

---

## outputs/

Generated files.

Examples:

* Extracted JSON
* Excel files
* Validation reports
* Application logs

---

## tests/

Automated testing.

Includes:

* Unit Tests
* Integration Tests
* End-to-End Tests

---

## Design Principles

* Separate business logic from infrastructure.
* Keep modules independent and reusable.
* Centralize schema definitions.
* Store prompts separately from application code.
* Organize sample data and outputs for easy testing.
* Make the project easy to extend with new modules and integrations.
