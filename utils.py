import pdfkit
from xlsxwriter import Workbook
from io import BytesIO
import os
from flask import render_template, send_file

def _get_pdfkit_config():
    path = os.environ.get('WKHTMLTOPDF_PATH', r'C:/Program Files/wkhtmltopdf/bin/wkhtmltopdf.exe')
    try:
        return pdfkit.configuration(wkhtmltopdf=path)
    except Exception as e:
        raise RuntimeError(f"wkhtmltopdf not configured at '{path}': {e}")


def generate_pdf_summary(summary, device_name, device_type, start_date, end_date):
    # Render the summary template
    rendered = render_template('pdf_summary_template.html', 
                               summary=summary, 
                               device_name=device_name, 
                               device_type=device_type,
                               start_date=start_date, 
                               end_date=end_date)

    # Generate the PDF from the HTML template using pdfkit
    try:
        pdf = pdfkit.from_string(rendered, False, configuration=_get_pdfkit_config())
    except Exception as e:
        return (f"PDF generation failed: {e}", 500)

    return send_file(
        BytesIO(pdf),
        download_name='iot_summary_report.pdf',
        as_attachment=True,
        mimetype='application/pdf'
    )


# Function to generate Excel file
def generate_excel(rows):
    output = BytesIO()
    workbook = Workbook(output, {'in_memory': True})
    worksheet = workbook.add_worksheet()

    # Write the headers
    worksheet.write(0, 0, 'Timestamp')
    worksheet.write(0, 1, 'Parameter Data')

    # Write the data
    for idx, row in enumerate(rows, 1):
        worksheet.write(idx, 0, row[1])  # Timestamp
        worksheet.write(idx, 1, row[0])  # Param Data

    workbook.close()
    output.seek(0)

    return send_file(output, download_name='data.xlsx', as_attachment=True)


# Function to generate PDF with graph and table
# Generate PDF with a graph and tabular data
def generate_pdf(rows, topic_name, start_date, end_date):
    rendered = render_template('pdf_template.html', 
                               rows=rows, 
                               topic_name=topic_name, 
                               start_date=start_date, 
                               end_date=end_date)
    
    # Generate the PDF from the HTML template using pdfkit
    try:
        pdf = pdfkit.from_string(rendered, False, configuration=_get_pdfkit_config())
    except Exception as e:
        return (f"PDF generation failed: {e}", 500)
    
    # Prepare the PDF to be sent as a download
    response = send_file(
        BytesIO(pdf),
        download_name='iot_data_report.pdf',
        as_attachment=True,
        mimetype='application/pdf'
    )
    
    return response
