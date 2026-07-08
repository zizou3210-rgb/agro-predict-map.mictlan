# Feature Hero

English | Español

---

## <a name="english"></a>English

### 1. Installation

#### With Poetry (recommended for development)

1.  **Install Python 3.12**: Make sure you have Python 3.12 installed.
2.  **Install Poetry**: Follow the instructions on the official Poetry website.
3.  **Set up the environment**: From the project root, run:
    ```bash
    poetry install
    ```

#### With pip (for end-users)

1.  **Create and activate a virtual environment (recommended)**:
    ```bash
    python -m venv .venv
    source .venv/bin/activate # On Linux/macOS
    # .venv\Scripts\activate # On Windows
    ```
2.  **Install the package**: From the project root:
    ```bash
    pip install .
    ```

Once installed, you can run commands with `poetry run featurehero <command>` or `featurehero <command>` if using pip in an activated environment.

### 2. Data Transformation (`transform`)

This command preprocesses your data, allowing you to transform date or categorical columns.

**Syntax:**
```bash
featurehero transform --file <path> --type <type> --columns <col1> [<col2> ...] [--out <filename>]
```
*   `--type`: Transformation type. Can be `date`, `date_seasonal`, `category`, `dummy`, `log1p`, or `sqrt`.
*   `--columns`: One or more columns to transform.
*   `--out`: (Optional) Name for the output file. By default, a `_transformed` suffix is added.

#### Date Transformation (`date`)
Converts a date column into multiple numerical features like year, month, day, day of the week, etc.

**Example:**
```bash
# Transform the 'order_date' column
featurehero transform --file data.csv --type date --columns order_date
```

#### Seasonal Date Transformation (`date_seasonal`)
Converts date columns in `MM/yyyy` format into dummy variables for year and month.

**Example:**
```bash
# Transform the 'planting_month' column using MM/yyyy input
featurehero transform --file data.csv --type date_seasonal --columns planting_month
```

#### Category Transformation (`category`)
Converts columns with text or categories into numerical values (Label Encoding).

**Example:**
```bash
# Transform 'product_type' and 'region' and save to a new file
featurehero transform --file data.csv --type category --columns product_type region --out processed_data.csv
```

#### Dummy Variable Transformation (`dummy`)
Converts categorical columns into one-hot encoded dummy variables.

**Example:**
```bash
# Transform 'product_type' and 'region' into dummy variables
featurehero transform --file data.csv --type dummy --columns product_type region --out processed_data.csv
```

#### Logarithmic Transformation (`log1p`)
Adds a new column with the natural logarithm of `x + 1`, useful for positively
skewed variables with zeros.

Rules:
*   Keeps the original column.
*   Creates a new column named `<column>_log1p`.
*   Preserves missing values.
*   Fails if the column contains negative or non-numeric values.

When to use it:
*   When the variable has strong positive skew.
*   When many observations are concentrated at low values and a smaller group extends to larger values.
*   When zeros are present and a classic `log(x)` would not be valid.

Examples:
*   `0 -> log1p(0) = 0`
*   `1 -> log1p(1) = 0.6931`
*   `10 -> log1p(10) = 2.3979`
*   `25 -> log1p(25) = 3.2581`

```bash
# Transform 'Farmers total land area (acres)' with log1p
featurehero transform --file data.csv --type log1p --columns "Farmers total land area (acres)" --out processed_data.csv
```

#### Square Root Transformation (`sqrt`)
Adds a new column with the square root of the selected variable, useful for
count-like variables with moderate positive skew.

Rules:
*   Keeps the original column.
*   Creates a new column named `<column>_sqrt`.
*   Preserves missing values.
*   Fails if the column contains negative or non-numeric values.

When to use it:
*   When the variable behaves like a count or density-like measure.
*   When the variable has moderate positive skew.
*   When you want a softer compression of large values than a logarithm.

Examples:
*   `0 -> sqrt(0) = 0`
*   `1 -> sqrt(1) = 1`
*   `4 -> sqrt(4) = 2`
*   `9 -> sqrt(9) = 3`
*   `16 -> sqrt(16) = 4`

Note:
*   `log1p` and `sqrt` are transformations, not missing-value imputation methods. Missing values remain missing.

```bash
# Transform 'Plant stand ; plot 1' with square root
featurehero transform --file data.csv --type sqrt --columns "Plant stand ; plot 1" --out processed_data.csv
```

### 3. Run Optimization (`run`)

Executes the genetic algorithm for feature selection and Machine Learning model optimization.

**Basic Syntax:**
```bash
featurehero run --file <path_to_file> --column <target_column>
```

**Example:**
```bash
featurehero run --file 'data/gold_price.csv' --column 'Adj Close'
```

### 4. Job Monitoring (`jobs`)

Allows you to manage processes running in the background.

#### List Active Jobs
Shows running processes, their PIDs, and details.
```bash
featurehero jobs --list
```

#### Stop a Job
Terminates a background process using its PID.
```bash
featurehero jobs --stop <PID>
```

### 5. Advanced `run` Command Options

#### Background Execution (`--background`)
Runs the optimization process in the background, freeing up the terminal and saving progress to a log file.

**Example:**
```bash
featurehero run --file 'data/prices.csv' --column 'price' --background
```

#### Custom Parameters (`--params`)
Allows you to adjust the genetic algorithm's parameters, such as the number of generations or population size, via a JSON string.

**Valid Parameters:**
*   `number_generation` (integer > 10): Number of generations the algorithm will run.
*   `number_population` (integer > 0): Population size in each generation.

**Example:**
```bash
# Run with 50 generations and a population of 200 individuals
featurehero run --file 'data.csv' --column 'target' --params '{"number_generation": 50, "number_population": 200}'
```

---

## <a name="español"></a>Español

### 1. Instalación

#### Con Poetry (recomendado para desarrollo)

1.  **Instalar Python 3.12**: Asegúrate de tener Python 3.12 instalado.
2.  **Instalar Poetry**: Sigue las instrucciones en el sitio web oficial de Poetry.
3.  **Configurar el entorno**: Desde la raíz del proyecto, ejecuta:
    ```bash
    poetry install
    ```

#### Con pip (para usuarios finales)

1.  **Crear y activar un entorno virtual (recomendado)**:
    ```bash
    python -m venv .venv
    source .venv/bin/activate # En Linux/macOS
    # .venv\Scripts\activate # En Windows
    ```
2.  **Instalar el paquete**: Desde la raíz del proyecto:
    ```bash
    pip install .
    ```

Una vez instalado, puedes ejecutar los comandos con `poetry run featurehero <comando>` o `featurehero <comando>` si usas pip en un entorno activado.

### 2. Transformación de Datos (`transform`)

Este comando preprocesa tus datos, permitiendo transformar columnas de fechas o categóricas.

**Sintaxis:**
```bash
featurehero transform --file <ruta> --type <tipo> --columns <col1> [<col2> ...] [--out <nombre_archivo>]
```
*   `--type`: Tipo de transformación. Puede ser `date`, `date_seasonal`, `category`, `dummy`, `log1p` o `sqrt`.
*   `--columns`: Una o más columnas a transformar.
*   `--out`: (Opcional) Nombre para el archivo de salida. Por defecto, se añade el sufijo `_transformed`.

#### Transformación de Fechas (`date`)
Convierte una columna de fecha en múltiples características numéricas como año, mes, día, etc.

**Ejemplo:**
```bash
# Transformar la columna 'order_date'
featurehero transform --file data.csv --type date --columns order_date
```

#### Transformación Estacional de Fechas (`date_seasonal`)
Convierte columnas con formato `MM/yyyy` a variables dummy de año y mes.

**Ejemplo:**
```bash
# Transformar la columna 'planting_month' usando entrada MM/yyyy
featurehero transform --file data.csv --type date_seasonal --columns planting_month
```

#### Transformación de Etiquetas (`category`)
Convierte columnas con texto o categorías en valores numéricos (Label Encoding).

**Ejemplo:**
```bash
# Transformar 'product_type' y 'region' y guardar en un nuevo archivo
featurehero transform --file data.csv --type category --columns product_type region --out processed_data.csv
```

#### Transformación a Variables Dummy (`dummy`)
Convierte columnas categóricas en variables dummy con one-hot encoding.

**Ejemplo:**
```bash
# Transformar 'product_type' y 'region' a variables dummy
featurehero transform --file data.csv --type dummy --columns product_type region --out processed_data.csv
```

#### Transformación Logarítmica (`log1p`)
Agrega una nueva columna con el logaritmo natural de `x + 1`, útil para
variables con asimetría positiva y presencia de ceros.

Reglas:
*   Conserva la columna original.
*   Crea una nueva columna llamada `<columna>_log1p`.
*   Mantiene los valores vacíos.
*   Falla si la columna contiene valores negativos o no numéricos.

Cuándo usarla:
*   Cuando la variable tiene asimetría positiva fuerte.
*   Cuando muchas observaciones se concentran en valores bajos y un grupo menor se extiende hacia valores altos.
*   Cuando existen ceros y un `log(x)` clásico no sería válido.

Ejemplos:
*   `0 -> log1p(0) = 0`
*   `1 -> log1p(1) = 0.6931`
*   `10 -> log1p(10) = 2.3979`
*   `25 -> log1p(25) = 3.2581`

```bash
# Transformar 'Farmers total land area (acres)' con log1p
featurehero transform --file data.csv --type log1p --columns "Farmers total land area (acres)" --out processed_data.csv
```

#### Transformación De Raíz Cuadrada (`sqrt`)
Agrega una nueva columna con la raíz cuadrada de la variable seleccionada,
útil para variables tipo conteo con asimetría positiva moderada.

Reglas:
*   Conserva la columna original.
*   Crea una nueva columna llamada `<columna>_sqrt`.
*   Mantiene los valores vacíos.
*   Falla si la columna contiene valores negativos o no numéricos.

Cuándo usarla:
*   Cuando la variable se comporta como conteo o medida de densidad simple.
*   Cuando la asimetría positiva es moderada.
*   Cuando se quiere comprimir los valores altos de forma más suave que con un logaritmo.

Ejemplos:
*   `0 -> sqrt(0) = 0`
*   `1 -> sqrt(1) = 1`
*   `4 -> sqrt(4) = 2`
*   `9 -> sqrt(9) = 3`
*   `16 -> sqrt(16) = 4`

Nota:
*   `log1p` y `sqrt` son transformaciones, no métodos de imputación de valores faltantes. Los vacíos permanecen vacíos.

```bash
# Transformar 'Plant stand ; plot 1' con raíz cuadrada
featurehero transform --file data.csv --type sqrt --columns "Plant stand ; plot 1" --out processed_data.csv
```

### 3. Ejecutar Optimización (`run`)

Ejecuta el algoritmo genético para la selección de características y optimización de modelos de Machine Learning.

**Sintaxis Básica:**
```bash
featurehero run --file <ruta_al_archivo> --column <columna_objetivo>
```

**Ejemplo:**
```bash
featurehero run --file 'data/precio_oro.csv' --column 'Adj Close'
```

### 4. Monitoreo de Tareas (`jobs`)

Permite administrar los procesos que se ejecutan en segundo plano.

#### Listar Tareas Activas
Muestra los procesos en ejecución, su PID y detalles.
```bash
featurehero jobs --list
```

#### Detener una Tarea
Finaliza un proceso en segundo plano usando su PID.
```bash
featurehero jobs --stop <PID>
```

### 5. Opciones Avanzadas del Comando `run`

#### Ejecución en Segundo Plano (`--background`)
Ejecuta el proceso de optimización en segundo plano, liberando la terminal y guardando el progreso en un archivo de log.

**Ejemplo:**
```bash
featurehero run --file 'data/precios.csv' --column 'precio' --background
```

#### Parámetros Personalizados (`--params`)
Permite ajustar los parámetros del algoritmo genético, como el número de generaciones o el tamaño de la población, a través de un string JSON.

**Parámetros Válidos:**
*   `number_generation` (entero > 10): Número de generaciones que ejecutará el algoritmo.
*   `number_population` (entero > 0): Tamaño de la población en cada generación.

**Ejemplo:**
```bash
# Ejecutar con 50 generaciones y una población de 200 individuos
featurehero run --file 'data.csv' --column 'target' --params '{"number_generation": 50, "number_population": 200}'
```
<<<<<<< Updated upstream
To get information from spseficic command you can run 
```bash
poetry run featurehero <comando> --help
# Ejemplo: poetry run featurehero run --help
```

## 2. Desarrollo y Modificación del Proyecto

Esta sección es para quienes desean contribuir o modificar el código fuente de `Feature Hero`.

### 2.1. Configuración del Entorno de Desarrollo

1.  **Clonar el repositorio**:
    ```bash
    git clone <URL_DEL_REPOSITORIO>
    cd phen_ga_desktop # O el nombre de tu directorio
    ```
2.  **Instalar Python 3.12**: Asegúrate de tener Python 3.12 o una versión compatible.
3.  **Instalar Poetry**: Sigue las instrucciones en python-poetry.org.
4.  **Configurar el entorno del proyecto**: Desde la raíz del proyecto, ejecuta:
    ```bash
    poetry install --verbose
    ```
    Esto instalará todas las dependencias y el propio proyecto en modo editable, lo que te permitirá modificar el código y ver los cambios reflejados inmediatamente.

### 2.2. Building the Package

To build the distribution packages (sdist and wheel) that can be published or installed with `pip`:

```bash
poetry build
```
Los archivos generados se encontrarán en el directorio `dist/`.

### 2.3. Consideraciones al Modificar el Código

*   **Code Formatting**: It is recommended to follow Python's style conventions (PEP 8). Consider using tools like `black` for automatic formatting and `pylint` or `flake8` for static code analysis.
*   **Updating Dependencies**: If you add or modify dependencies, use `poetry add <package>` or `poetry update` to manage the `pyproject.toml` and `poetry.lock` files.
*   **Updating the Version**: If you change the version in `pyproject.toml`, remember that `poetry install` will update the virtual environment to reflect the new version.
<<<<<<< HEAD
=======
>>>>>>> Stashed changes
=======


>>>>>>> 2025.11.1
