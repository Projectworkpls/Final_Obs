import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
import calendar
from datetime import datetime
import io
import google.generativeai as genai
from config import Config


class MonthlyReportGenerator:
    def __init__(self, supabase_client):
        self.supabase = supabase_client
        # Initialize Gemini AI for report generation
        genai.configure(api_key=Config.GOOGLE_API_KEY)

    def get_month_data(self, child_id, year, month):
        """Fetch all observations for a specific child in a given month"""
        start_date = f"{year}-{month:02d}-01"
        if month == 12:
            end_date = f"{year + 1}-01-01"
        else:
            end_date = f"{year}-{month + 1:02d}-01"

        try:
            response = self.supabase.table('observations').select("*") \
                .eq("student_id", child_id) \
                .gte("date", start_date) \
                .lt("date", end_date) \
                .execute()
            return response.data
        except Exception as e:
            return []

    def get_goal_progress(self, child_id, year, month):
        """Get goal progress data for the specified month"""
        start_date = f"{year}-{month:02d}-01"
        if month == 12:
            end_date = f"{year + 1}-01-01"
        else:
            end_date = f"{year}-{month + 1:02d}-01"

        try:
            goals_response = self.supabase.table('goals').select("*") \
                .eq("child_id", child_id) \
                .execute()
            goals = goals_response.data

            goal_progress = []
            for goal in goals:
                alignments_response = self.supabase.table('goal_alignments').select("*") \
                    .eq("goal_id", goal['id']) \
                    .execute()
                alignments = alignments_response.data

                relevant_alignments = []
                for alignment in alignments:
                    report_response = self.supabase.table('observations').select("date") \
                        .eq("id", alignment['report_id']) \
                        .execute()

                    if report_response.data:
                        report_date = report_response.data[0]['date']
                        if start_date <= report_date < end_date:
                            relevant_alignments.append(alignment)

                if relevant_alignments:
                    avg_score = sum(a['alignment_score'] for a in relevant_alignments) / len(relevant_alignments)
                    progress_trend = [a['alignment_score'] for a in relevant_alignments]

                    goal_progress.append({
                        'goal_text': goal['goal_text'],
                        'avg_score': avg_score,
                        'progress_trend': progress_trend,
                        'num_observations': len(relevant_alignments),
                        'status': goal.get('status', 'active')
                    })

            return goal_progress
        except Exception as e:
            return []

    def get_strength_areas(self, observations):
        """Extract and count strength areas from observations"""
        strength_counts = {}

        for obs in observations:
            if obs.get('strengths'):
                try:
                    strengths = json.loads(obs['strengths']) if isinstance(obs['strengths'], str) else obs['strengths']
                    for strength in strengths:
                        strength_counts[strength] = strength_counts.get(strength, 0) + 1
                except:
                    pass

        return dict(sorted(strength_counts.items(), key=lambda x: x[1], reverse=True))

    def get_development_areas(self, observations):
        """Extract and count development areas from observations"""
        development_counts = {}

        for obs in observations:
            if obs.get('areas_of_development'):
                try:
                    areas = json.loads(obs['areas_of_development']) if isinstance(obs['areas_of_development'], str) else \
                        obs['areas_of_development']
                    for area in areas:
                        development_counts[area] = development_counts.get(area, 0) + 1
                except:
                    pass

        return dict(sorted(development_counts.items(), key=lambda x: x[1], reverse=True))

    def generate_observation_frequency_chart(self, observations):
        """Generate a chart showing the frequency of observations by date"""
        date_counts = {}

        for obs in observations:
            date = obs.get('date', '')
            if date:
                date_counts[date] = date_counts.get(date, 0) + 1

        if not date_counts:
            return None

        df = pd.DataFrame([
            {"date": date, "count": count}
            for date, count in date_counts.items()
        ])

        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')

        fig = px.bar(
            df,
            x='date',
            y='count',
            title='Observation Frequency by Date',
            labels={'date': 'Date', 'count': 'Number of Observations'}
        )

        return fig

    def generate_strengths_chart(self, strength_counts):
        """Generate a chart showing the frequency of different strengths"""
        if not strength_counts:
            return None

        top_strengths = dict(list(strength_counts.items())[:10])

        df = pd.DataFrame([
            {"strength": strength, "count": count}
            for strength, count in top_strengths.items()
        ])

        fig = px.bar(
            df,
            x='count',
            y='strength',
            title='Top Strengths Observed',
            labels={'strength': 'Strength', 'count': 'Frequency'},
            orientation='h'
        )

        return fig

    def generate_development_areas_chart(self, development_counts):
        """Generate a chart showing the frequency of different development areas"""
        if not development_counts:
            return None

        top_areas = dict(list(development_counts.items())[:10])

        df = pd.DataFrame([
            {"area": area, "count": count}
            for area, count in top_areas.items()
        ])

        fig = px.bar(
            df,
            x='count',
            y='area',
            title='Areas for Development',
            labels={'area': 'Development Area', 'count': 'Frequency'},
            orientation='h'
        )

        return fig

    def generate_goal_progress_chart(self, goal_progress):
        """Generate a chart showing progress on goals"""
        if not goal_progress:
            return None

        fig = make_subplots(rows=len(goal_progress), cols=1,
                            subplot_titles=[g['goal_text'][:50] + '...' for g in goal_progress],
                            vertical_spacing=0.1)

        for i, goal in enumerate(goal_progress):
            fig.add_trace(
                go.Bar(
                    x=[goal['avg_score']],
                    y=['Average Score'],
                    orientation='h',
                    name=f"Goal {i + 1}",
                    showlegend=False
                ),
                row=i + 1, col=1
            )

            fig.add_shape(
                type="line",
                x0=10, y0=-0.5,
                x1=10, y1=0.5,
                line=dict(color="green", width=2, dash="dash"),
                row=i + 1, col=1
            )

        fig.update_layout(
            title_text="Goal Progress",
            height=200 * len(goal_progress),
            margin=dict(l=0, r=0, t=50, b=0)
        )

        return fig

    def generate_monthly_summary(self, observations, goal_progress):
        """Generate a text summary of the monthly progress"""
        if not observations:
            return "No observations recorded this month."

        num_observations = len(observations)
        num_goals_with_progress = len(goal_progress)

        if goal_progress:
            avg_goal_score = sum(g['avg_score'] for g in goal_progress) / len(goal_progress)
            highest_goal = max(goal_progress, key=lambda x: x['avg_score'])
            lowest_goal = min(goal_progress, key=lambda x: x['avg_score'])
        else:
            avg_goal_score = 0
            highest_goal = None
            lowest_goal = None

        summary = f"""
        ### Monthly Progress Summary

        **Total Observations:** {num_observations}
        **Goals Tracked:** {num_goals_with_progress}
        **Average Goal Progress:** {avg_goal_score:.1f}/10
        """

        if highest_goal:
            summary += f"""
            **Strongest Goal Area:** {highest_goal['goal_text'][:50]}... (Score: {highest_goal['avg_score']:.1f}/10)
            **Goal Needing Most Support:** {lowest_goal['goal_text'][:50]}... (Score: {lowest_goal['avg_score']:.1f}/10)
            """

        return summary

    # NEW: Generate monthly summary in JSON format with graph suggestions
    def generate_monthly_summary_json_format(self, observations, goal_progress, child_name, year, month):
        """Generate monthly summary in the new JSON format with graph recommendations"""
        try:
            # Prepare data for analysis
            observation_texts = []
            all_strengths = []
            all_developments = []
            all_recommendations = []

            for obs in observations:
                observation_texts.append(obs.get('observations', ''))

                # Parse strengths, developments, and recommendations
                if obs.get('strengths'):
                    try:
                        strengths = json.loads(obs['strengths']) if isinstance(obs['strengths'], str) else obs[
                            'strengths']
                        all_strengths.extend(strengths)
                    except:
                        pass

                if obs.get('areas_of_development'):
                    try:
                        developments = json.loads(obs['areas_of_development']) if isinstance(
                            obs['areas_of_development'], str) else obs['areas_of_development']
                        all_developments.extend(developments)
                    except:
                        pass

                if obs.get('recommendations'):
                    try:
                        recommendations = json.loads(obs['recommendations']) if isinstance(obs['recommendations'],
                                                                                           str) else obs[
                            'recommendations']
                        all_recommendations.extend(recommendations)
                    except:
                        pass

            # Calculate metrics for graphs
            total_observations = len(observations)
            active_goals = len([g for g in goal_progress if g.get('status') == 'active'])
            completed_goals = len([g for g in goal_progress if g.get('status') == 'achieved'])

            # Count frequency of strengths and development areas
            strength_counts = {}
            for strength in all_strengths:
                strength_counts[strength] = strength_counts.get(strength, 0) + 1

            development_counts = {}
            for dev in all_developments:
                development_counts[dev] = development_counts.get(dev, 0) + 1

            # Calculate weekly observation trends
            weekly_trends = self._calculate_weekly_trends(observations, year, month)

            # Calculate learning progress metrics
            learning_metrics = self._calculate_learning_metrics(observations)

            # Prepare graph data suggestions
            graph_suggestions = []

            if total_observations > 0:
                graph_suggestions.append({
                    "type": "line_chart",
                    "title": "Weekly Observation Trends",
                    "description": f"Shows observation frequency across {len(weekly_trends)} weeks in the month",
                    "data": weekly_trends,
                    "xAxis": "Week",
                    "yAxis": "Number of Observations"
                })

                graph_suggestions.append({
                    "type": "bar_chart",
                    "title": "Daily Learning Activities",
                    "description": f"Distribution of {total_observations} learning sessions throughout the month",
                    "data": {"total_sessions": total_observations},
                    "insights": f"Average of {total_observations / 30:.1f} sessions per day"
                })

            if strength_counts:
                graph_suggestions.append({
                    "type": "pie_chart",
                    "title": "Strength Areas Distribution",
                    "description": f"Breakdown of {len(strength_counts)} different strength categories",
                    "data": dict(list(strength_counts.items())[:8]),
                    "insights": f"Most frequent strength: {max(strength_counts.keys(), key=strength_counts.get)}"
                })

                graph_suggestions.append({
                    "type": "donut_chart",
                    "title": "Top 5 Strengths Focus",
                    "description": "Concentrated view of primary strength areas",
                    "data": dict(list(strength_counts.items())[:5])
                })

            if development_counts:
                graph_suggestions.append({
                    "type": "horizontal_bar",
                    "title": "Development Priority Areas",
                    "description": f"Focus areas requiring attention with frequency analysis",
                    "data": dict(list(development_counts.items())[:6]),
                    "insights": f"Primary development focus: {max(development_counts.keys(), key=development_counts.get)}"
                })

            if goal_progress:
                goal_completion_rate = (completed_goals / (active_goals + completed_goals)) * 100 if (
                                                                                                                 active_goals + completed_goals) > 0 else 0

                graph_suggestions.append({
                    "type": "gauge_chart",
                    "title": "Goal Achievement Rate",
                    "description": f"Monthly goal completion progress",
                    "data": {
                        "completion_rate": goal_completion_rate,
                        "completed": completed_goals,
                        "active": active_goals,
                        "total": active_goals + completed_goals
                    },
                    "insights": f"{goal_completion_rate:.1f}% completion rate this month"
                })

                graph_suggestions.append({
                    "type": "progress_bars",
                    "title": "Individual Goal Progress",
                    "description": "Detailed progress tracking for each goal",
                    "data": [{"goal": g['goal_text'][:30], "progress": g['avg_score']} for g in goal_progress[:5]]
                })

            # Add learning engagement metrics if available
            if learning_metrics:
                graph_suggestions.append({
                    "type": "radar_chart",
                    "title": "Learning Engagement Profile",
                    "description": "Multi-dimensional view of learning engagement",
                    "data": learning_metrics,
                    "insights": "Comprehensive engagement across different learning domains"
                })

            # Create comprehensive prompt for JSON generation
            monthly_prompt = f"""
            You are an AI assistant for a learning observation system. Generate a comprehensive monthly report based on the provided observation data for educational assessment and progress tracking.

            REPORTING PERIOD: {calendar.month_name[month]} {year}
            STUDENT: {child_name}
            TOTAL OBSERVATIONS: {total_observations}
            GOALS STATUS: {active_goals} active, {completed_goals} completed
            LEARNING SESSIONS ANALYZED: {len(observation_texts)}

            OBSERVATION SAMPLE DATA: {json.dumps(observation_texts[:3], indent=2)}
            STRENGTHS IDENTIFIED: {list(strength_counts.keys())[:8]}
            DEVELOPMENT AREAS: {list(development_counts.keys())[:6]}
            WEEKLY TRENDS: {weekly_trends}

            QUANTIFIABLE METRICS FOR VISUAL ANALYTICS:
            {json.dumps(graph_suggestions, indent=2)}

            Format your response as JSON with the following structure:
            {{
              "studentName": "{child_name}",
              "studentId": "Monthly-{year}-{month:02d}-Report",
              "className": "Monthly Learning Progress Assessment",
              "date": "{calendar.month_name[month]} {year}",
              "observations": "Comprehensive monthly learning summary combining all {total_observations} observation sessions. Detail the student's learning journey throughout {calendar.month_name[month]}, highlighting key educational milestones, skill development patterns, engagement levels, and notable learning breakthroughs. Include specific examples of learning activities, problem-solving approaches, creative expressions, and social interactions observed during the month.",
              "strengths": {json.dumps(list(strength_counts.keys())[:8])},
              "areasOfDevelopment": {json.dumps(list(development_counts.keys())[:6])},
              "recommendations": ["Specific actionable recommendations for {calendar.month_name[month + 1 if month < 12 else 1]} based on observed learning patterns", "Suggested learning activities to reinforce strengths", "Targeted interventions for development areas", "Parent engagement strategies", "Environmental modifications to support learning"],
              "monthlyMetrics": {{
                "totalObservations": {total_observations},
                "activeGoals": {active_goals},
                "completedGoals": {completed_goals},
                "goalCompletionRate": {(completed_goals / (active_goals + completed_goals)) * 100 if (active_goals + completed_goals) > 0 else 0},
                "topStrengths": {dict(list(strength_counts.items())[:5])},
                "developmentFocus": {dict(list(development_counts.items())[:5])},
                "weeklyTrends": {weekly_trends},
                "averageSessionsPerWeek": {total_observations / 4.3 if total_observations > 0 else 0}
              }},
              "learningAnalytics": {{
                "engagementLevel": "High/Medium/Low based on observation frequency and quality",
                "learningVelocity": "Assessment of learning pace and skill acquisition speed",
                "socialDevelopment": "Progress in social skills and peer interactions",
                "cognitiveGrowth": "Intellectual development and problem-solving abilities",
                "creativityIndex": "Creative expression and innovative thinking patterns",
                "independenceLevel": "Self-directed learning and autonomous task completion"
              }},
              "suggestedGraphs": {graph_suggestions},
              "progressInsights": [
                "Key learning breakthroughs achieved this month",
                "Patterns in learning preferences and optimal learning conditions",
                "Social and emotional development observations",
                "Areas showing accelerated growth",
                "Challenges overcome and resilience demonstrated"
              ]
            }}

            For the observations field, provide a comprehensive narrative like:
            "Throughout {calendar.month_name[month]} {year}, {child_name} demonstrated remarkable growth across multiple learning domains. The student engaged in {total_observations} documented learning sessions, showing consistent curiosity and enthusiasm for discovery-based learning. Key highlights include [specific learning achievements], where the student mastered [specific skills] through hands-on exploration and guided inquiry. Notable progress was observed in [subject areas], with the student showing particular aptitude for [specific skills]. The learning journey included diverse activities such as [examples from observations], demonstrating the student's ability to connect concepts across different domains and apply learning in practical contexts."

            Include detailed quantifiable metrics and suggest appropriate visual analytics for comprehensive representation of the student's monthly learning progress. Be creative in extracting meaningful patterns, learning trajectories, and developmental insights from the observation data.

            Ensure all recommendations are specific, actionable, and tailored to the student's individual learning profile and developmental stage.
            """

            # Generate the report using AI
            model = genai.GenerativeModel('gemini-2.0-flash')
            response = model.generate_content([
                {"role": "user", "parts": [{"text": monthly_prompt}]}
            ])

            return response.text

        except Exception as e:
            return f"Error generating monthly summary: {str(e)}"

    def _calculate_weekly_trends(self, observations, year, month):
        """Calculate weekly observation trends for the month"""
        weekly_counts = [0, 0, 0, 0, 0]  # Up to 5 weeks in a month

        for obs in observations:
            try:
                obs_date = datetime.strptime(obs.get('date', ''), '%Y-%m-%d')
                # Calculate which week of the month
                week_of_month = (obs_date.day - 1) // 7
                if week_of_month < 5:
                    weekly_counts[week_of_month] += 1
            except:
                continue

        return {f"Week {i + 1}": count for i, count in enumerate(weekly_counts) if count > 0}

    def _calculate_learning_metrics(self, observations):
        """Calculate learning engagement and progress metrics"""
        if not observations:
            return {}

        # Calculate various learning metrics
        total_sessions = len(observations)

        # Analyze themes and curiosity seeds
        themes = []
        curiosity_seeds = []

        for obs in observations:
            if obs.get('theme_of_day'):
                themes.append(obs['theme_of_day'])
            if obs.get('curiosity_seed'):
                curiosity_seeds.append(obs['curiosity_seed'])

        return {
            "session_frequency": total_sessions,
            "theme_diversity": len(set(themes)),
            "curiosity_engagement": len(set(curiosity_seeds)),
            "learning_consistency": "High" if total_sessions > 15 else "Medium" if total_sessions > 8 else "Low"
        }

    def generate_excel_report(self, observations, goal_progress, strength_counts, development_counts):
        """Generate Excel report with multiple sheets"""
        buffer = io.BytesIO()

        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            # Summary sheet
            summary_data = {
                "Metric": ["Total Observations", "Goals Tracked", "Average Goal Score"],
                "Value": [len(observations), len(goal_progress),
                          sum(g['avg_score'] for g in goal_progress) / len(goal_progress) if goal_progress else 0]
            }
            summary_df = pd.DataFrame(summary_data)
            summary_df.to_excel(writer, sheet_name='Summary', index=False)

            # Strengths sheet
            if strength_counts:
                strengths_df = pd.DataFrame([
                    {"Strength": strength, "Count": count}
                    for strength, count in strength_counts.items()
                ])
                strengths_df.to_excel(writer, sheet_name='Strengths', index=False)

            # Development areas sheet
            if development_counts:
                development_df = pd.DataFrame([
                    {"Development Area": area, "Count": count}
                    for area, count in development_counts.items()
                ])
                development_df.to_excel(writer, sheet_name='Development Areas', index=False)

            # Goal progress sheet
            if goal_progress:
                goals_df = pd.DataFrame([
                    {"Goal": g['goal_text'], "Average Score": g['avg_score'], "Observations": g['num_observations']}
                    for g in goal_progress
                ])
                goals_df.to_excel(writer, sheet_name='Goal Progress', index=False)

        buffer.seek(0)
        return buffer
