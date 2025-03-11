# SolarEdge Emporia AutoCharge

## Overview
This project integrates SolarEdge and Emporia systems to automate the charging of electric vehicles. It aims to optimize energy usage by leveraging solar power and managing grid consumption efficiently.
Thanks to [magico13/PyEmVue](https://github.com/magico13/PyEmVue) for the Emporia API integration.

## Features
- Automated EV charging based on solar production
- Real-time monitoring of energy consumption
- Customizable charging schedules
- Integration with SolarEdge and Emporia APIs 

## Installation
1. Clone the repository:
  ```sh
  git clone https://github.com/itayke/solaredge-emporia-autocharge.git
  ```
2. Navigate to the project directory:
  ```sh
  cd solaredge-emporia-autocharge
  ```
3. Install the required dependencies:
  ```sh
  pip install -r requirements.txt
  ```

## Configuration
Create a `.env` file in the root directory and add your API keys and configuration settings:
```env
SOLAREDGE_SITE=site_number
SOLAREDGE_KEY='site_key'
EMPORIA_USER='emporia_username_email'
EMPORIA_PASSWORD='emporia_password'
```

## Usage
To see the available command line arguments, run the script with the `help` flag:
```sh
python solaredge-emporia-autocharge.py help
```

Run in background with default values:
```sh
python solaredge-emporia-autocharge.py &
```

Run in background with 10 minute frequency + maximum amp value of 50:
```sh
python solaredge-emporia-autocharge.py freq=600 max_amps=48 &
```

## License
This project is licensed under the GNU General Public License v3.0. See the [LICENSE](LICENSE) file for details.

## Contact
For any questions or support, please open an issue on the GitHub repository or mail itay at untame dot com
