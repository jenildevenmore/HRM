import datetime

from rest_framework import serializers

from .models import DynamicField, DynamicModel, DynamicRecord


class DynamicModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = DynamicModel
        fields = ('id', 'client', 'name', 'slug', 'show_in_employee_form', 'created_at', 'updated_at')
        read_only_fields = ('id', 'created_at', 'updated_at')


class DynamicFieldSerializer(serializers.ModelSerializer):
    class Meta:
        model = DynamicField
        fields = (
            'id',
            'dynamic_model',
            'name',
            'key',
            'field_type',
            'required',
            'visible_to_users',
            'choices_json',
            'sort_order',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'created_at', 'updated_at')

    def validate_choices_json(self, value):
        if value in (None, ''):
            return []
        if not isinstance(value, list):
            raise serializers.ValidationError('choices_json must be a list.')
        return value


class DynamicRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = DynamicRecord
        fields = ('id', 'dynamic_model', 'employee', 'data', 'created_at', 'updated_at')
        read_only_fields = ('id', 'created_at', 'updated_at')

    def validate(self, attrs):
        dynamic_model = attrs.get('dynamic_model') or getattr(self.instance, 'dynamic_model', None)
        if not dynamic_model:
            raise serializers.ValidationError({'dynamic_model': 'This field is required.'})
        employee = attrs.get('employee', getattr(self.instance, 'employee', None))
        if employee and employee.client_id != dynamic_model.client_id:
            raise serializers.ValidationError(
                {'employee': 'Employee must belong to the same client as dynamic_model.'}
            )

        incoming = attrs.get('data', {})
        if not isinstance(incoming, dict):
            raise serializers.ValidationError({'data': 'data must be an object.'})

        existing = self.instance.data if self.instance else {}
        merged = {**existing, **incoming}
        attrs['data'] = self._validate_data(dynamic_model, merged, partial=self.partial)
        self._validate_attendance_rules(dynamic_model, employee, attrs['data'], existing)
        return attrs

    def _validate_attendance_rules(self, dynamic_model, employee, merged_data, existing_data):
        if str(dynamic_model.slug or '').lower() != 'attendance':
            return

        if not employee:
            raise serializers.ValidationError({'employee': 'Employee is required for attendance records.'})

        attendance_date = str(merged_data.get('attendance_date') or '').strip()
        if not attendance_date:
            raise serializers.ValidationError({'data': {'attendance_date': 'Attendance date is required.'}})

        same_day_qs = DynamicRecord.objects.filter(
            dynamic_model_id=dynamic_model.id,
            employee_id=employee.id,
            data__attendance_date=attendance_date,
        )
        if self.instance:
            same_day_qs = same_day_qs.exclude(id=self.instance.id)
        if same_day_qs.exists():
            raise serializers.ValidationError(
                {'data': {'attendance_date': 'Only one attendance record per employee per day is allowed.'}}
            )

        check_in_existing = existing_data.get('check_in') if isinstance(existing_data, dict) else None
        check_out_existing = existing_data.get('check_out') if isinstance(existing_data, dict) else None
        check_in_new = merged_data.get('check_in')
        check_out_new = merged_data.get('check_out')

        if self.instance and check_in_existing and check_in_new and str(check_in_new) != str(check_in_existing):
            raise serializers.ValidationError({'data': {'check_in': 'Punch-in can be saved only once per day.'}})

        if self.instance and check_out_existing and check_out_new and str(check_out_new) != str(check_out_existing):
            raise serializers.ValidationError({'data': {'check_out': 'Punch-out can be saved only once per day.'}})

    def _validate_data(self, dynamic_model, data, partial=False):
        fields = list(dynamic_model.fields.all())
        field_map = {f.key: f for f in fields}

        unknown_keys = sorted(set(data.keys()) - set(field_map.keys()))
        if unknown_keys:
            raise serializers.ValidationError({'data': f'Unknown keys: {", ".join(unknown_keys)}'})

        errors = {}
        cleaned = {}

        for field in fields:
            value = data.get(field.key)
            if field.required and (value is None or value == ''):
                if not partial:
                    errors[field.key] = 'This field is required.'
                continue

            if value is None or value == '':
                continue

            valid, converted, message = self._coerce_value(field, value)
            if not valid:
                errors[field.key] = message
                continue

            if field.choices_json and converted not in field.choices_json:
                errors[field.key] = f'Value must be one of: {field.choices_json}'
                continue

            cleaned[field.key] = converted

        if errors:
            raise serializers.ValidationError({'data': errors})

        return cleaned

    def _coerce_value(self, field, value):
        ft = field.field_type
        if ft == 'text':
            return True, str(value), ''
        if ft == 'number':
            try:
                number = float(value)
                # keep ints as ints when possible
                if number.is_integer():
                    return True, int(number), ''
                return True, number, ''
            except (TypeError, ValueError):
                return False, None, 'Must be a valid number.'
        if ft == 'boolean':
            if isinstance(value, bool):
                return True, value, ''
            if str(value).lower() in ('true', '1', 'yes'):
                return True, True, ''
            if str(value).lower() in ('false', '0', 'no'):
                return True, False, ''
            return False, None, 'Must be true/false.'
        if ft == 'date':
            if isinstance(value, datetime.date):
                return True, value.isoformat(), ''
            try:
                parsed = datetime.date.fromisoformat(str(value))
                return True, parsed.isoformat(), ''
            except ValueError:
                return False, None, 'Must be ISO date (YYYY-MM-DD).'
        if ft == 'email':
            email_field = serializers.EmailField()
            try:
                return True, email_field.run_validation(value), ''
            except serializers.ValidationError:
                return False, None, 'Must be a valid email address.'
        if ft in ('file', 'image'):
            as_text = str(value).strip()
            if not as_text:
                return False, None, 'Must be a valid file path or URL.'
            return True, as_text, ''
        return False, None, 'Unsupported field type.'
